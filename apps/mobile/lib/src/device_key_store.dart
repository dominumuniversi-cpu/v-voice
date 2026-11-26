/// Хранилище ключа устройства.
///
/// Зачем отдельно от адреса: сервер с замком (`VV_DEVICE_TOKENS`) не пустит без ключа, а ввести его
/// было негде — человек видел «не удалось подключиться» и не знал, что делать. Ключ лежит отдельно
/// от адреса, чтобы очистка адреса не стирала ключ и наоборот.
abstract class DeviceKeyStore {
  Future<String?> read();
  Future<void> write(String key);
}

/// Хранилище в памяти: для тестов и до первого сохранения.
class MemoryDeviceKeyStore implements DeviceKeyStore {
  MemoryDeviceKeyStore([this._value]);

  String? _value;

  @override
  Future<String?> read() async => _value;

  @override
  Future<void> write(String key) async => _value = key.trim();
}

/// Что считать годным ключом. Пусто — значит «замка нет», и это допустимо.
///
/// Пробелы по краям — обычная беда при копировании из чата: обрежем, но не будем делать вид,
/// что ключ неверный, когда дело в одном пробеле.
String? deviceKeyProblem(String raw) {
  final value = raw.trim();
  if (value.isEmpty) return null;
  if (value.length < 8) return 'Ключ слишком короткий — проверьте, что скопировали его целиком.';
  if (value.contains(' ')) return 'В ключе не должно быть пробелов.';
  return null;
}
