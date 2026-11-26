/// Модель разбора разговора: выжимка и элементы (задачи/встречи/напоминания).
///
/// Правило проекта (FR-9): элемент без цитаты не существует. Поэтому `Item.fromJson`
/// отбрасывает элементы без непустой цитаты, а не показывает их без доказательства:
/// человек, который не может проверить, откуда взялась задача, задачи не примет.
class Digest {
  Digest({required this.summary, required this.decisions, required this.openQuestions, required this.items, required this.participants, required this.model});

  final List<String> summary;
  final List<String> decisions;
  final List<String> openQuestions;
  final List<Item> items;

  /// Кто участвовал: [имя, вердикт]. Вердикт — это и есть проверка «свой голос или чужой»:
  /// без него человек не поймёт, почему часть сказанного не попала в задачи.
  final List<List<String>> participants;
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
    final rawParticipants = json['participants'];
    final participants = <List<String>>[];
    if (rawParticipants is List) {
      for (final raw in rawParticipants) {
        if (raw is! Map) continue;
        final m = Map<String, dynamic>.from(raw);
        final name = (m['name'] ?? m['speaker'] ?? '').toString();
        final verdict = (m['verdict'] ?? 'member').toString();
        if (name.isNotEmpty) participants.add(<String>[name, verdict]);
      }
    }
    return Digest(
      participants: participants,
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
  Item({required this.id, required this.kind, required this.title, required this.owner, required this.due, required this.quote, required this.startS, this.endS = 0, required this.approved});

  /// Идентификатор элемента. Нужен при отправке наружу: без него сервер не знает, что именно уходит,
  /// и отвергает элемент как «не годный к отправке».
  final String id;

  final String kind;
  final String title;
  final String owner;
  final String due;
  final String quote;
  final double startS;

  /// Конец фрагмента в записи, секунды. Может отсутствовать в старых ответах сервера.
  final double endS;

  bool approved;

  /// Тело для сервера при отправке наружу. Поле approved передаётся явно:
  /// сервер обязан видеть, что человек подтвердил задачу, а не приложение решило за него.
  Map<String, dynamic> toJson() => {
        'id': id,
        'kind': kind,
        'title': title,
        'owner': owner,
        'due_at': due,
        'evidence_quote': quote,
        'start_s': startS,
        'end_s': endS,
        'approved': approved,
      };

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
      id: (json['id'] ?? '').toString().isNotEmpty
          ? json['id'].toString()
          // Стабильный запасной вариант: заголовок + время начала. Не случайный — иначе
          // повторный разбор давал бы новые id для тех же задач.
          : (title + '@' + (json['start_s'] ?? 0).toString()),
      endS: (json['end_s'] is num) ? (json['end_s'] as num).toDouble() : 0,
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
