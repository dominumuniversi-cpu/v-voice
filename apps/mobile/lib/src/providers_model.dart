/// Каталог провайдеров и пресетов для экрана подключения моделей (FR-24..FR-26).
///
/// Данные лежат здесь, а не в виджете: подписи, цены и подсказки — это то, что человек читает
/// перед покупкой ключа, и это нужно проверять отдельно от вёрстки.
class ProviderInfo {
  const ProviderInfo({required this.id, required this.title, required this.kind, required this.note, required this.needsKey});

  final String id;
  final String title;
  final String kind; // asr | llm
  final String note;
  final bool needsKey;
}

const List<ProviderInfo> kProviders = [
  ProviderInfo(
    id: 'gigaam',
    title: 'GigaAM-v3 (свой сервер)',
    kind: 'asr',
    note: 'Лучшее качество для русского, нужен свой компьютер с видеокартой. Ничего не уходит наружу.',
    needsKey: false,
  ),
  ProviderInfo(
    id: 'speechmatics',
    title: 'Speechmatics (облако)',
    kind: 'asr',
    note: 'Онлайн, задержка меньше секунды, различает говорящих. Оплата по часам.',
    needsKey: true,
  ),
  ProviderInfo(
    id: 'deepgram',
    title: 'Deepgram (облако)',
    kind: 'asr',
    note: 'Онлайн, дешевле Speechmatics, но русский заметно слабее.',
    needsKey: true,
  ),
  ProviderInfo(
    id: 'deepseek',
    title: 'DeepSeek (разбор)',
    kind: 'llm',
    note: 'Дешёвый и точный разбор на русском. Данные уходят в облако.',
    needsKey: true,
  ),
  ProviderInfo(
    id: 'gigachat',
    title: 'GigaChat (разбор)',
    kind: 'llm',
    note: 'Российское облако: данные не покидают страну. Дороже.',
    needsKey: true,
  ),
  ProviderInfo(
    id: 'ollama',
    title: 'Ollama на своём компьютере',
    kind: 'llm',
    note: 'Всё локально, ключ не нужен. Нужен мощный компьютер.',
    needsKey: false,
  ),
];

/// Пресеты: человек выбирает намерение, а не десяток параметров.
const Map<String, Map<String, String>> kPresets = {
  'точно': {'title': 'Точно', 'asr': 'speechmatics', 'llm': 'deepseek', 'hint': 'Лучшее качество, данные в облаке'},
  'дёшево': {'title': 'Быстро и дёшево', 'asr': 'deepgram', 'llm': 'deepseek', 'hint': 'Экономно, качество русского ниже'},
  'приватно': {'title': 'Только локально', 'asr': 'gigaam', 'llm': 'ollama', 'hint': 'Ничего не уходит с вашей машины'},
};

/// Проверка перед отправкой в сеть: повторяет правила сервера, чтобы не гонять заведомо плохой ключ.
class KeyCheck {
  static String? problem(String provider, String key) {
    final info = kProviders.where((p) => p.id == provider).toList();
    if (info.isEmpty) return 'Неизвестный провайдер: ' + provider;
    if (!info.first.needsKey) return null;
    final trimmed = key.trim();
    if (trimmed.isEmpty) return 'Ключ не введён.';
    if (trimmed.contains(' ') || trimmed.contains('\n')) return 'В ключе есть пробел или перевод строки.';
    if (trimmed.length < 16) return 'Ключ слишком короткий — похоже, скопирована только часть.';
    return null;
  }

  /// Есть ли провайдеры выбранного вида (asr/llm) — для проверки полноты настройки.
  static bool hasKind(String kind) => kProviders.any((p) => p.kind == kind);
}
