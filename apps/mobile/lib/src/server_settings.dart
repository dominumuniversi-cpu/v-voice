/// Адрес сервера: то, что человек вводит один раз в настройках.
///
/// Почему с проверкой: без неё появляется «сервер недоступен» на любой опечатке, и человек
/// не понимает, что виноват не интернет, а забытая буква или лишний слэш в конце.
class ServerSettings {
  ServerSettings({required this.baseUrl, this.deviceToken = ''});

  final String baseUrl;

  /// Токен устройства: сервер пускает только своих. Пустой — сервер открыт (режим разработки).
  final String deviceToken;

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
    // Завершающий слэш — не ошибка: normalize() его уберёт. Отказывать здесь значит
    // требовать от человека ручной правки того, что машина правит сама.
    return null;
  }

  /// Не ошибка, а предупреждение: по HTTP разговор идёт открытым текстом, и всё сказанное
  /// в кафе или офисе может читать посторонний. Запрещать не надо — на своей машине http://localhost
  /// законен и удобен. Но и молчать нельзя: человек иначе не узнает, чем платит за простоту.
  static String? insecureNote(String raw) {
    final uri = Uri.tryParse(raw.trim());
    if (uri == null || uri.scheme != 'http') return null;
    final local = uri.host == 'localhost' || uri.host == '127.0.0.1' || uri.host == '10.0.2.2';
    if (local) return null;
    return 'Адрес без шифрования: звук и расшифровка идут открытым текстом. Для своего компьютера это нормально, для общего Wi-Fi — нет.';
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
