/// Адрес сервера: то, что человек вводит один раз в настройках.
///
/// Почему с проверкой: без неё появляется «сервер недоступен» на любой опечатке, и человек
/// не понимает, что виноват не интернет, а забытая буква или лишний слэш в конце.
class ServerSettings {
  ServerSettings({required this.baseUrl});

  final String baseUrl;

  static const List<String> presets = [
    'https://v-voice.vernadsky-npc.ru',
    'https://192.168.8.49/v-voice',
    'http://127.0.0.1:8900',
  ];

  /// Возвращает причину, если адрес не годится, или null, если всё в порядке.
  static String? problem(String raw) {
    final text = raw.trim();
    if (text.isEmpty) return 'Адрес сервера не заполнен.';
    if (!text.startsWith('http://') && !text.startsWith('https://')) {
      return 'Адрес должен начинаться с http:// или https://';
    }
    final uri = Uri.tryParse(text);
    if (uri == null || uri.host.isEmpty) return 'Похоже, в адресе ошибка: не удалось разобрать домен.';
    if (uri.hasQuery || uri.hasFragment) return 'Уберите знак «?» и «#» из адреса сервера.';
    if (text.endsWith('/')) return 'Уберите слэш в конце адреса.';
    return null;
  }

  /// Нормализованный адрес без завершающего слэша — для склейки с путями API.
  static String normalize(String raw) {
    var text = raw.trim();
    while (text.endsWith('/')) {
      text = text.substring(0, text.length - 1);
    }
    return text;
  }
}
