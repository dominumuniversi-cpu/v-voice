/// Модель разбора разговора: выжимка и элементы (задачи/встречи/напоминания).
///
/// Правило проекта (FR-9): элемент без цитаты не существует. Поэтому `Item.fromJson`
/// отбрасывает элементы без непустой цитаты, а не показывает их без доказательства:
/// человек, который не может проверить, откуда взялась задача, задачи не примет.
class Digest {
  Digest({required this.summary, required this.decisions, required this.openQuestions, required this.items, required this.participants, required this.model, this.truncated = false, this.summaryMissing = false, this.summaryHidden = 0, this.topic = '', this.rejected = const [], this.costRub, this.sentSeconds, this.budgetRub, this.droppedNoise = 0, this.droppedInvented = 0, this.droppedByVad = 0, this.errors = const []});

  final List<String> summary;
  final List<String> decisions;
  final List<String> openQuestions;
  final List<Item> items;

  /// Кто участвовал: [имя, вердикт]. Вердикт — это и есть проверка «свой голос или чужой»:
  /// без него человек не поймёт, почему часть сказанного не попала в задачи.
  final List<List<String>> participants;

  /// Предложения модели, которые не подтвердились дословной цитатой. Человек должен видеть,
  /// почему задач меньше, чем прозвучало, а не думать, что модель промолчала.
  final List<String> rejected;

  /// Модель не выделила ни одного пункта выжимки. Это факт о разборе, а не пустое место:
  /// «нечего сказать» и «не справилась» выглядят на экране одинаково, если флаг не читать.
  final bool summaryMissing;

  /// Одна строка «о чём был разговор». Пустая, если модель её не дала.
  final String topic;

  /// Разобрана только часть разговора: он длиннее, чем помещается в один проход модели.
  /// Показывать «готово» на половине — значит соврать про встречу.
  final bool truncated;

  /// Сколько пунктов выжимки не показано из-за краткости. Ноль — показано всё.
  final int summaryHidden;
  final String model;

  /// Из отчёта об отсеве делаем строку для человека: заголовок и причина, без служебных индексов.
  static List<String> rejectedFrom(Object? value) {
    if (value is! List) return const [];
    final out = <String>[];
    for (final r in value) {
      if (r is! Map) continue;
      final title = (r['title'] ?? '').toString().trim();
      final reason = (r['reason'] ?? '').toString().trim();
      if (title.isEmpty && reason.isEmpty) continue;
      out.add(reason.isEmpty ? title : (title.isEmpty ? reason : title + ' — ' + reason));
    }
    return List<String>.unmodifiable(out);
  }

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
      truncated: json['truncated'] == true,
      summaryHidden: (json['summary_hidden'] is num) ? (json['summary_hidden'] as num).toInt() : 0,
      topic: (json['topic'] ?? '').toString(),
      rejected: rejectedFrom(json['rejected']),
      summaryMissing: json['summary_missing'] == true,
      costRub: json['cost_rub'] is num ? (json['cost_rub'] as num).toDouble() : null,
      sentSeconds: json['sent_seconds'] is num ? (json['sent_seconds'] as num).toDouble() : null,
      budgetRub: json['budget_exceeded'] == true && json['budget_rub'] is num
          ? (json['budget_rub'] as num).toDouble()
          : null,
      droppedNoise: json['dropped_noise'] is num ? (json['dropped_noise'] as num).toInt() : 0,
      droppedInvented: json['dropped_invented'] is num ? (json['dropped_invented'] as num).toInt() : 0,
      droppedByVad: json['dropped_by_vad'] is num ? (json['dropped_by_vad'] as num).toInt() : 0,
      errors: list(json['errors']),
    );
  }

  /// Стоимость встречи в рублях. null — сервер не знает тарифа, и тогда мы не показываем «0 ₽»:
  /// выдуманная цена хуже отсутствующей, потому что на неё начнут опираться.
  final double? costRub;

  /// Предел на одну встречу, если он задан и превышен. null — всё в порядке или предела нет.
  final double? budgetRub;

  /// Сколько кадров (по 20 мс) отсечено как шум. Человеку это нужно знать: иначе он решит,
  /// что в тихой части разговора просто «ничего не сказали», хотя звук был и его выбросили.
  final int droppedNoise;

  /// Сколько строк распознавание придумало в тишине. Показывает, насколько шумная запись.
  final int droppedInvented;

  /// Сколько кадров (20 мс) не ушло в распознавание, потому что это была тишина.
  /// Это главное число про экономию: именно эти кадры не оплачены провайдеру.
  final int droppedByVad;

  /// Ошибки частичного разбора. Пусто — разбор прошёл целиком.
  final List<String> errors;

  /// Сколько секунд аудио ушло в распознавание. Нужно, чтобы человек видел объём даже без тарифа.
  final double? sentSeconds;

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

  static const _months = ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];

  /// Срок в человеческом виде: «27 ноя, 10:00».
  /// Модель отдаёт ISO8601, и человек, увидев «2026-11-27T10:00:00», не станет вчитываться —
  /// а для напоминания срок и есть главное. Непонятную дату не выдумываем: отдаём как есть.
  String get dueHuman {
    final parsed = DateTime.tryParse(due);
    if (parsed == null) return due;
    final day = parsed.day.toString();
    final hh = parsed.hour.toString().padLeft(2, '0');
    final mm = parsed.minute.toString().padLeft(2, '0');
    final hasTime = parsed.hour != 0 || parsed.minute != 0;
    return day + ' ' + _months[parsed.month - 1] + (hasTime ? ', ' + hh + ':' + mm : '');
  }

  /// У встречи и напоминания время — не украшение: напоминание без срока не напомнит никогда,
  /// встреча без времени не встанет в календарь. Молча рисовать их наравне с датированными —
  /// значит обещать то, чего приложение не сделает.
  bool get missingTime => due.trim().isEmpty && (kind == 'meeting' || kind == 'reminder');

  /// Что показать вместо срока, если его нет. Пусто — если срок есть или он не обязателен.
  String get missingTimeNote => missingTime ? 'без времени' : '';

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
