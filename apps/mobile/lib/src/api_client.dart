import 'dart:convert';

import 'digest_model.dart';

/// Транспорт HTTP: подменяется в тестах, поэтому логика клиента проверяется без сети.
abstract class HttpTransport {
  /// Возвращает (код ответа, тело).
  Future<(int, String)> post(String path, Map<String, dynamic> body);
  Future<(int, String)> get(String path);
}

/// Клиент нашего сервера (API v1).
///
/// Правила, которые здесь закреплены:
///  1. Любой ответ, кроме 200, превращается в понятную ошибку с кодом — приложение не молчит.
///  2. Тело читается как UTF-8: русский текст в ответах не должен превращаться в кракозябры.
///  3. Проверяемый ключ отправляется и НЕ сохраняется на телефоне: держим только в памяти экрана.
class ApiClient {
  ApiClient({required this.transport, required this.baseUrl});

  /// Что сервер знает о моделях: готов ли разбор речи и понимание.
  ///
  /// Зачем это на телефоне: ключи живут на сервере, и человек должен видеть там ли их подключили,
  /// иначе он будет искать поле для ключа, которого больше нет.
  Future<Map<String, dynamic>?> fetchHealth() async {
    final (code, body) = await transport.get('/api/v1/health');
    if (code != 200) return null;
    final data = _safeDecode(body);
    final settings = data['settings'];
    return settings is Map ? Map<String, dynamic>.from(settings) : null;
  }

  /// Отправляет одобренные человеком задачи во внешние системы.
  ///
  /// Почему сюда приходит уже одобренное: сервер отвергает неодобренное намеренно.
  /// Приложение не решает за человека, что попадёт в его задачник.
  Future<(int sent, int failed, String problem)> exportItems(
    String sessionId,
    List<Item> items,
    Map<String, String> targets,
  ) async {
    final approved = items.where((i) => i.approved).toList();
    if (approved.isEmpty) return (0, 0, 'Ни одна задача не одобрена — отправлять нечего.');
    final (code, body) = await transport.post(
      '/api/v1/sessions/' + sessionId + '/export',
      {
        'targets': targets,
        'items': approved.map((i) => i.toJson()).toList(),
      },
    );
    final data = _safeDecode(body);
    if (code != 200) {
      final message = (data['message'] ?? '').toString();
      return (0, 0, message.isNotEmpty ? message : 'Сервер ответил кодом ' + code.toString() + '.');
    }
    final sent = (data['sent'] is num) ? (data['sent'] as num).toInt() : 0;
    final failed = (data['failed'] is num) ? (data['failed'] as num).toInt() : 0;
    return (sent, failed, failed > 0 ? 'Не дошли до ' + failed.toString() + ' адресатов.' : '');
  }

  /// Открывает сессию заранее, до появления записи.
  ///
  /// Зачем: живому тексту нужен идентификатор, а он раньше появлялся только при загрузке
  /// готового файла — то есть живой текст не мог начаться никогда.
  Future<String?> openSession() async {
    final (code, body) = await transport.post('/api/v1/sessions/open', {});
    final data = _safeDecode(body);
    if (code != 200) {
      lastLiveProblem = 'Сервер не открыл сессию (код ' + code.toString() + ').';
      return null;
    }
    final id = (data['session_id'] ?? '').toString();
    return id.isEmpty ? null : id;
  }

  /// Отправляет кусок звука и возвращает накопленный текст разговора.
  ///
  /// Молчаливый отказ при обрыве: живой текст вспомогательный, и падение одного куска
  /// не должно стирать то, что уже показано человеку.
  /// Сколько кусков звука не дошло до сервера. Показывается человеку — тишина в тексте
  /// не должна выглядеть как «там ничего не говорили».
  int chunksLost = 0;

  Future<String?> sendLiveChunk(String sessionId, List<int> pcm) async {
    if (pcm.isEmpty) return null;
    final (code, body) = await transport.post(
      '/api/v1/sessions/' + sessionId + '/stream',
      {'pcm_base64': base64Encode(pcm)},
    );
    if (code != 200) {
      lastLiveProblem = 'Сервер не принял кусок звука (код ' + code.toString() + ').';
      return null;
    }
    final data = _safeDecode(body);
    final text = (data['text'] ?? '').toString();
    lastLiveProblem = '';
    return text.isEmpty ? null : text;
  }

  /// Почему последний кусок живого текста не прошёл. Пустая строка — всё хорошо.
  String lastLiveProblem = '';

  /// Просит сервер разобрать загруженную запись.
  ///
  /// Почему отдельный шаг: разбор может идти минуты, и держать экран в ожидании одного запроса —
  /// значит получить таймаут там, где всё работает. Здесь только запуск; результат читается отдельно.
  Future<bool> startAnalysis(String sessionId) async {
    lastAnalysisProblem = '';
    final (code, body) = await transport.post('/api/v1/sessions/' + sessionId + '/analyze', {});
    final data = _safeDecode(body);
    // 200 — запущено; 503/404/502 — настоящая проблема, о ней говорим честно.
    if (code == 200) return true;
    final message = (data['message'] ?? '').toString();
    lastAnalysisProblem = message.isNotEmpty ? message : 'Сервер ответил кодом ' + code.toString() + '.';
    return false;
  }

  /// Почему разбор не удалось запустить. Пустая строка — всё хорошо или запуска не было.
  String lastAnalysisProblem = '';

  /// Отправляет запись на сервер и возвращает идентификатор сессии (или null с причиной в lastUploadProblem).
  ///
  /// Почему base64: транспорт уже проверен на JSON-путях, и отдельный двоичный протокол
  /// означал бы ещё один непроверенный кусок. Цена — примерно треть лишнего объёма, которую
  /// платим только в момент загрузки.
  Future<String?> uploadSession(List<int> audioBytes) async {
    lastUploadProblem = '';
    if (audioBytes.isEmpty) {
      lastUploadProblem = 'Запись пустая — отправлять нечего.';
      return null;
    }
    final encoded = base64Encode(audioBytes);
    final (code, body) = await transport.post('/api/v1/sessions', {'audio_base64': encoded});
    final data = _safeDecode(body);
    if (code != 200) {
      final message = (data['message'] ?? '').toString();
      lastUploadProblem = message.isNotEmpty ? message : 'Сервер ответил кодом ' + code.toString() + '.';
      return null;
    }
    final id = (data['session_id'] ?? '').toString();
    if (id.isEmpty) {
      lastUploadProblem = 'Сервер не вернул идентификатор сессии.';
      return null;
    }
    return id;
  }

  /// Почему последняя загрузка не удалась. Пустая строка — всё хорошо или загрузки не было.
  String lastUploadProblem = '';

  /// Почему последний запрос разбора ничего не вернул.
  /// Пустая строка — всё в порядке или запроса ещё не было.
  /// Без этого экран показывал пустоту, и человек читал её как «приложение не поняло разговор».
  String lastDigestProblem = '';

  final HttpTransport transport;
  final String baseUrl;

  /// Проверка ключа провайдера (FR-24).
  Future<(String verdict, String message)> probe(String provider, String apiKey) async {
    final (code, body) = await transport.post('/api/v1/probe', {'provider': provider, 'api_key': apiKey});
    if (code == 200) {
      final data = jsonDecode(body) as Map<String, dynamic>;
      return ((data['verdict'] ?? 'unknown').toString(), (data['message'] ?? '').toString());
    }
    if (code == 400) {
      final data = _safeDecode(body);
      return ('rejected', (data['message'] ?? 'Сервер отклонил запрос проверки.').toString());
    }
    return ('rejected', 'Сервер ответил кодом ' + code.toString() + '.');
  }

  /// Проверка элемента разбора против расшифровки — тем же правилом, что на сервере.
  Future<(bool ok, String reason)> validateItem(Map<String, dynamic> item, String transcript) async {
    final (code, body) = await transport.post('/api/v1/items/validate', {'item': item, 'transcript': transcript});
    if (code == 200) return (true, '');
    final data = _safeDecode(body);
    if (code == 422) return (false, (data['reason'] ?? 'цитаты нет в расшифровке').toString());
    return (false, (data['message'] ?? 'Ошибка сервера: ' + code.toString()).toString());
  }

  /// Готовый разбор с сервера. Возвращает null, если сервер не дал выжимку — приложение не выдумывает.
  /// Расшифровка в выбранном формате: txt, md, srt, vtt. Возвращает текст файла как есть.
  ///
  /// Почему не через fetchDigest: расшифровка — это файл, а не JSON. Человеку нужен тот же текст,
  /// который он потом откроет в заметках или смонтирует в видео, а не обёртка вокруг него.
  Future<(String? text, String problem)> fetchTranscript(String sessionId, String format) async {
    final (code, body) = await transport
        .get('/api/v1/sessions/' + sessionId + '/transcript?format=' + format);
    if (code != 200) {
      final failed = _safeDecode(body);
      final message = (failed['message'] ?? '').toString();
      return (null, message.isNotEmpty ? message : 'Сервер ответил кодом ' + code.toString() + '.');
    }
    return (body, '');
  }

  Future<Digest?> fetchDigest(String sessionId) async {
    final (code, body) = await transport.get('/api/v1/sessions/' + sessionId + '/digest');
    if (code != 200) {
      // Не молчим: пустой экран без причины человек читает как «приложение не поняло».
      final failed = _safeDecode(body);
      final message = (failed['message'] ?? '').toString();
      lastDigestProblem = message.isNotEmpty ? message : 'Сервер ответил кодом ' + code.toString() + '.';
      return null;
    }
    final data = _safeDecode(body);
    if (data.isEmpty) {
      lastDigestProblem = 'Сервер прислал пустой ответ.';
      return null;
    }
    return Digest.fromJson(data);
  }

  Map<String, dynamic> _safeDecode(String body) {
    try {
      final decoded = jsonDecode(body);
      return decoded is Map<String, dynamic> ? decoded : <String, dynamic>{};
    } catch (_) {
      return <String, dynamic>{};
    }
  }
}
