import 'dart:async';

/// Состояния записи. Единый словарь с Android/iOS: idle | recording | paused | stopped.
enum RecordingState { idle, recording, paused, stopped, unavailable }

/// Абстракция нативного моста записи.
///
/// У нас две нативные реализации (Android Kotlin, iOS Swift) с одним контрактом
/// `vvoice/recording`: start() -> "ok" | "denied" | "not_allowed_in_background",
/// stop() -> "ok". Тесты подставляют фейковый мост, поэтому логика экрана проверяется
/// без телефона — это единственный способ проверить её здесь, где Flutter SDK нет.
abstract class RecordingBridge {
  Future<String> start();
  Future<String> stop();
  Stream<Map<String, dynamic>> get events;
}

/// Ошибки записи в человеческом виде: человек должен понимать, что случилось.
class RecordingError {
  static String explain(String code) {
    switch (code) {
      case 'denied':
        return 'Микрофон запрещён. Разрешите доступ в настройках телефона.';
      case 'not_allowed_in_background':
        return 'Запись можно начать только с открытого экрана приложения. Откройте его и нажмите «Слушаю» снова.';
      case 'mic_unavailable':
        return 'Микрофон занят другим приложением. Закройте его и попробуйте снова.';
      case 'session_failed':
      case 'engine_failed':
        return 'Не удалось включить запись на этом устройстве. Перезапустите приложение.';
      case 'write_failed':
      case 'disk_full':
        return 'Место на телефоне закончилось или память недоступна — запись остановлена. Освободите место и начните заново: уже записанное сохранено.';
      case 'recording_interrupted':
        return 'Запись прервана звонком или будильником. Если система разрешит, она продолжится сама.';
      case 'input_lost':
        return 'Пропал микрофон: отключились наушники или микрофон занят. Подключите его и начните заново.';
      case 'resume_failed':
        return 'Не удалось продолжить запись после звонка. Начните новую.';
      case 'paused':
        return 'Запись на паузе.';
      default:
        return 'Ошибка записи: ' + code;
    }
  }
}

/// Логика экрана «Слушаю».
///
/// Правила, которые здесь закреплены (и проверяются тестом):
///  1. Нельзя начать запись второй раз, пока идёт первая — двойное нажатие не создаёт две сессии.
///  2. При любом отказе состоянии остаётся idle, человеку показывается причина.
///  3. Живой текст обновляется только по событиям моста — никакого опроса таймером.
///  4. Остановка мгновенная: «Стоп» не спрашивает подтверждения и не блокирует экран.
class RecordingController {
  RecordingController(this.bridge);

  final RecordingBridge bridge;
  RecordingState state = RecordingState.idle;

  /// Уровень сигнала 0..1 из нативного слоя. Ноль — «ничего не слышим», не «тихо».
  /// Пока натив не присылает уровень, значение остаётся 0.
  double level = 0;
  String lastError = '';

  /// Путь к последней сохранённой записи (пустой, пока ничего не сохранено).
  /// Нужен, чтобы разбор знал, какую запись отправлять на сервер.
  String lastSavedPath = '';

  /// Последний кусок звука от натива (PCM 16 бит) и счётчик полученных кусков.
  /// Верхний слой забирает кусок и отправляет его на сервер; контроллер сам ничего не отправляет.
  List<int>? lastAudioChunk;

  /// Сколько кусков звука пришло. Ноль при включённой записи означает тишину в канале.
  int audioChunksReceived = 0;

  /// Длительность последней записи в миллисекундах.
  int lastDurationMs = 0;
  String liveText = '';

  /// Честное предупреждение о проблеме, из-за которой текст может быть неполным.
  /// Отдельно от liveText: человек должен видеть и сам текст, и оговорку к нему.
  String liveWarning = '';

  final StreamController<String> _changes = StreamController<String>.broadcast();
  Stream<String> get changes => _changes.stream;
  StreamSubscription<Map<String, dynamic>>? _sub;

  void bind() {
    _sub ??= bridge.events.listen((event) {
      if (event['type'] == 'state') {
        state = _parse(event['value'] as String?);
        _emit();
      } else if (event['type'] == 'error') {
        lastError = RecordingError.explain(event['code'] as String? ?? 'unknown');
        _emit();
      } else if (event['type'] == 'live') {
        // Живой текст может прийти и от натива (если распознавание пойдёт на устройстве),
        // и от серверного потока через тот же мост. Пустая строка не затирает сказанное.
        final text = event['value'] as String?;
        if (text != null && text.isNotEmpty) liveText = text;
        _emit();
      } else if (event['type'] == 'audio') {
        // Кусок звука для онлайн-распознавания. Не копим: держать в памяти всю запись —
        // верный способ уронить телефон на длинном разговоре.
        final pcm = event['pcm'];
        if (pcm is List<int> && pcm.isNotEmpty) {
          lastAudioChunk = pcm;
          audioChunksReceived++;
        }
      } else if (event['type'] == 'saved') {
        // Файл готов: путь приходит от натива сразу после финализации WAV.
        final path = event['path'] as String?;
        if (path != null && path.isNotEmpty) {
          lastSavedPath = path;
          final ms = event['duration_ms'];
          lastDurationMs = ms is num ? ms.toInt() : 0;
          _emit();
        }
      } else if (event['type'] == 'level') {
        // Натив присылает RMS (0..1). Неизвестный формат не должен ронять поток.
        final raw = event['value'];
        if (raw is num) level = raw.toDouble().clamp(0, 1).toDouble();
        _emit();
      }
    }, onError: (Object error) {
      lastError = 'Связь с записью потеряна: ' + error.toString();
      state = RecordingState.unavailable;
      _emit();
    }, cancelOnError: false);
    // Поток событий закрылся без явной ошибки — нативная часть «отвалилась». Молча оставлять
    // «запись идёт» нельзя: человек должен видеть, что его больше не слушают.
    _sub!.onDone(() {
      if (state == RecordingState.recording || state == RecordingState.paused) {
        lastError = 'Нативная часть записи остановилась. Проверьте, что приложение не выгружено системой.';
        state = RecordingState.unavailable;
        _emit();
      }
    });
  }

  Future<void> start() async {
    if (state == RecordingState.recording) return;
    lastError = '';
    final result = await bridge.start();
    if (result == 'ok') {
      state = RecordingState.recording;
    } else {
      state = RecordingState.idle;
      lastError = RecordingError.explain(result);
    }
    _emit();
  }

  Future<void> stop() async {
    if (state != RecordingState.recording && state != RecordingState.paused) return;
    await bridge.stop();
    state = RecordingState.stopped;
    _emit();
  }

  RecordingState _parse(String? value) {
    switch (value) {
      case 'recording':
        return RecordingState.recording;
      case 'paused':
        return RecordingState.paused;
      case 'stopped':
        return RecordingState.stopped;
      default:
        return RecordingState.idle;
    }
  }

  void _emit() {
    if (!_changes.isClosed) _changes.add(state.name);
  }

  Future<void> dispose() async {
    await _sub?.cancel();
    await _changes.close();
  }
}
