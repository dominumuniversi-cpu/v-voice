import 'package:shared_preferences/shared_preferences.dart';

import 'key_value_store.dart';

/// Хранилище поверх shared_preferences: переживает перезапуск приложения.
///
/// Тонкий адаптер: правила (что сохранять, когда забывать) живут в ConsentStore и ServerSettingsKeeper.
class PrefsKeyValueStore implements KeyValueStore {
  @override
  Future<String?> read(String key) async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(key);
  }

  @override
  Future<void> write(String key, String value) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(key, value);
  }

  @override
  Future<void> remove(String key) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(key);
  }
}
