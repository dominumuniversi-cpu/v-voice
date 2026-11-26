/// Хранилище адреса сервера.
///
/// Абстракция над хранилищем нужна, чтобы правило «плохой адрес не сохраняем» проверялось
/// тестом, а не верой: реальная реализация поверх shared_preferences подставляется в приложении.
abstract class ServerStore {
  Future<String?> read();
  Future<void> write(String url);
}

/// Простое хранилище в памяти: используется тестами и до первого сохранения.
class MemoryServerStore implements ServerStore {
  MemoryServerStore([this._value]);

  String? _value;

  @override
  Future<String?> read() async => _value;

  @override
  Future<void> write(String url) async => _value = url;
}

/// Правило сохранения: негодный адрес не записывается, а старый не затирается.
///
/// Это важнее, чем кажется: если сохранить опечатку, приложение на следующем запуске
/// будет молча ходить в никуда, и человек решит, что сломан сервер.
class ServerSettingsKeeper {
  ServerSettingsKeeper({required this.store, required this.validate, required this.normalize});

  final ServerStore store;
  final String? Function(String) validate;
  final String Function(String) normalize;

  /// Возвращает причину отказа или null при успехе.
  Future<String?> save(String raw) async {
    final problem = validate(raw);
    if (problem != null) return problem;
    await store.write(normalize(raw));
    return null;
  }

  /// Адрес для запросов; fallback — если сохранённого нет или он оказался негодным.
  Future<String> load(String fallback) async {
    final stored = await store.read();
    if (stored == null || validate(stored) != null) return normalize(fallback);
    return normalize(stored);
  }
}
