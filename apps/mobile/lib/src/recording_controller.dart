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
        return 'Не удаётся писать звук на диск: возможно, закончилось место.';
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
  String lastError = '';
  String liveText = '';

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
        liveText = event['value'] as String? ?? liveText;
        _emit();
      }
    }, onError: (Object error) {
      lastError = 'Связь с записью потеряна: ' + error.toString();
      state = RecordingState.unavailable;
      _emit();
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
