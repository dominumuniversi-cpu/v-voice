/// Простое хранилище строк по ключу.
///
/// Одна абстракция на все пользовательские решения (адрес сервера, принятая версия согласия),
/// чтобы правила «что и когда сохранять» проверялись тестами без платформенных плагинов.
abstract class KeyValueStore {
  Future<String?> read(String key);
  Future<void> write(String key, String value);
  Future<void> remove(String key);
}

/// Хранилище в памяти: тесты и состояние до первого сохранения.
class MemoryKeyValueStore implements KeyValueStore {
  final Map<String, String> values = {};

  @override
  Future<String?> read(String key) async => values[key];

  @override
  Future<void> write(String key, String value) async => values[key] = value;

  @override
  Future<void> remove(String key) async => values.remove(key);
}
