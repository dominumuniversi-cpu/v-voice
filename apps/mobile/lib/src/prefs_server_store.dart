import 'package:shared_preferences/shared_preferences.dart';

import 'server_store.dart';

/// Хранилище адреса поверх shared_preferences: переживает перезапуск приложения.
///
/// Тонкий адаптер: правила «что сохранять» живут в ServerSettingsKeeper и проверяются тестами
/// без платформенных плагинов.
class PrefsServerStore implements ServerStore {
  static const String key = 'server_url';

  @override
  Future<String?> read() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(key);
  }

  @override
  Future<void> write(String url) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(key, url);
  }
}
