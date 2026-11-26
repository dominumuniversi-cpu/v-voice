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
