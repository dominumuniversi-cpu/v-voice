/// Модель разбора разговора: выжимка и элементы (задачи/встречи/напоминания).
///
/// Правило проекта (FR-9): элемент без цитаты не существует. Поэтому `Item.fromJson`
/// отбрасывает элементы без непустой цитаты, а не показывает их без доказательства:
/// человек, который не может проверить, откуда взялась задача, задачи не примет.
class Digest {
  Digest({required this.summary, required this.decisions, required this.openQuestions, required this.items, required this.model});

  final List<String> summary;
  final List<String> decisions;
  final List<String> openQuestions;
  final List<Item> items;
  final String model;

  static Digest fromJson(Map<String, dynamic> json) {
    List<String> list(Object? value) => value is List ? value.map((e) => e.toString()).toList(growable: false) : const [];
    final rawItems = json['items'];
    final items = <Item>[];
    if (rawItems is List) {
      for (final raw in rawItems) {
        if (raw is! Map) continue;
        final item = Item.fromJson(Map<String, dynamic>.from(raw));
        if (item != null) items.add(item);
      }
    }
    return Digest(
      summary: list(json['summary']),
      decisions: list(json['decisions']),
      openQuestions: list(json['open_questions'] ?? json['openQuestions']),
      items: items,
      model: (json['model'] ?? '').toString(),
    );
  }

  /// Сколько элементов отброшено как недоказуемые — показываем человеку честно.
  int droppedCount = 0;
}

class Item {
  Item({required this.kind, required this.title, required this.owner, required this.due, required this.quote, required this.startS, required this.approved});

  final String kind;
  final String title;
  final String owner;
  final String due;
  final String quote;
  final double startS;
  bool approved;

  /// Возвращает null, если элемент недоказуем (нет цитаты) или безымянный (нет заголовка).
  static Item? fromJson(Map<String, dynamic> json) {
    final quote = (json['quote'] ?? (json['evidence'] is Map ? (json['evidence'] as Map)['quote'] : ''))
        .toString()
        .trim();
    final title = (json['title'] ?? '').toString().trim();
    if (quote.isEmpty || title.isEmpty) return null;
    final evidence = json['evidence'] is Map ? json['evidence'] as Map : const {};
    final start = json['start_s'] ?? evidence['start_s'] ?? 0;
    return Item(
      kind: (json['kind'] ?? 'task').toString(),
      title: title,
      owner: (json['owner'] ?? '').toString(),
      due: (json['due_at'] ?? json['due'] ?? '').toString(),
      quote: quote,
      startS: start is num ? start.toDouble() : double.tryParse(start.toString()) ?? 0,
      approved: json['status'] == 'approved',
    );
  }

  /// Время в формате 05:12 — по нему человек находит место в записи.
  String get timecode {
    final total = startS.round();
    final m = (total ~/ 60).toString().padLeft(2, '0');
    final s = (total % 60).toString().padLeft(2, '0');
    return m + ':' + s;
  }

  String get kindLabel {
    switch (kind) {
      case 'meeting':
        return 'Встреча';
      case 'reminder':
        return 'Напоминание';
      case 'decision':
        return 'Решение';
      case 'question':
        return 'Вопрос';
      default:
        return 'Задача';
    }
  }
}
