import 'package:flutter_test/flutter_test.dart';
import 'package:v_voice/src/digest_model.dart';

void main() {
  group('Digest.fromJson', () {
    test('отсечённый шум и ошибки читаются', () {
      final digest = Digest.fromJson({
        'summary': ['x'],
        'dropped_noise': 1500,
        'dropped_invented': 2,
        'errors': ['noise_dropped: 1500'],
      });
      expect(digest.droppedNoise, 1500);
      expect(digest.droppedInvented, 2);
      expect(digest.errors.length, 1);
    });

    test('тишина, не ушедшая в распознавание, читается', () {
      final digest = Digest.fromJson({'summary': ['x'], 'dropped_by_vad': 3000});
      expect(digest.droppedByVad, 3000);
    });

    test('без шума и ошибок поля пустые, а не выдуманные', () {
      final digest = Digest.fromJson({'summary': ['x']});
      expect(digest.droppedNoise, 0);
      expect(digest.errors, isEmpty);
    });

    test('предел превышен — видно, сколько он составляет', () {
      final digest = Digest.fromJson({'summary': ['x'], 'cost_rub': 80.0, 'budget_exceeded': true, 'budget_rub': 50.0});
      expect(digest.budgetRub, 50.0);
    });

    test('в пределах предела — предупреждения нет', () {
      final digest = Digest.fromJson({'summary': ['x'], 'cost_rub': 10.0});
      expect(digest.budgetRub, isNull);
    });

    test('стоимость встречи читается, когда сервер её прислал', () {
      final digest = Digest.fromJson({'summary': ['x'], 'cost_rub': 12.5, 'sent_seconds': 1800.0});
      expect(digest.costRub, 12.5);
      expect(digest.sentSeconds, 1800.0);
    });

    test('без тарифа стоимость отсутствует, а не равна нулю', () {
      // Ноль означал бы «встреча бесплатна». Сервер в этом случае поле не присылает вовсе.
      final digest = Digest.fromJson({'summary': ['x'], 'sent_seconds': 600.0});
      expect(digest.costRub, isNull);
      expect(digest.sentSeconds, 600.0);
    });

    test('элемент без цитаты отбрасывается', () {
      final digest = Digest.fromJson({
        'summary': ['Обсудили смету'],
        'items': [
          {'kind': 'task', 'title': 'Отправить смету', 'quote': 'я отправлю смету завтра'},
          {'kind': 'task', 'title': 'Придумать что-то'},
          {'kind': 'task', 'title': 'Пустая цитата', 'quote': '   '},
        ],
      });
      expect(digest.items.length, 1);
      expect(digest.items.first.title, 'Отправить смету');
    });

    test('элемент без заголовка отбрасывается', () {
      final digest = Digest.fromJson({
        'items': [
          {'kind': 'task', 'quote': 'цитата есть, а заголовка нет'},
        ],
      });
      expect(digest.items, isEmpty);
    });

    test('цитата достаётся и из evidence, если пришла вложенно', () {
      final digest = Digest.fromJson({
        'items': [
          {'kind': 'reminder', 'title': 'Позвонить', 'evidence': {'quote': 'позвони в среду', 'start_s': 125}},
        ],
      });
      expect(digest.items.single.quote, 'позвони в среду');
      expect(digest.items.single.timecode, '02:05');
    });

    test('таймкод форматируется как минуты и секунды', () {
      final digest = Digest.fromJson({
        'items': [
          {'title': 'x', 'quote': 'y', 'start_s': 7},
        ],
      });
      expect(digest.items.single.timecode, '00:07');
    });

    test('пустой разбор не падает и не выдумывает', () {
      final digest = Digest.fromJson({});
      expect(digest.summary, isEmpty);
      expect(digest.items, isEmpty);
      expect(digest.model, '');
    });

    test('виды элементов подписаны по-русски', () {
      final digest = Digest.fromJson({
        'items': [
          {'title': 'a', 'quote': 'b', 'kind': 'meeting'},
          {'title': 'c', 'quote': 'd', 'kind': 'нечто'},
        ],
      });
      expect(digest.items.first.kindLabel, 'Встреча');
      expect(digest.items.last.kindLabel, 'Задача');
    });
  });

  test('элемент сериализуется для отправки с признаком одобрения', () {
    final item = Item.fromJson({
      'id': 'i7',
      'title': 'Отправить смету',
      'kind': 'task',
      'quote': 'я отправлю смету Ивану',
      'start_s': 2.0,
      'end_s': 4.0,
    })!;
    item.approved = true;
    final json = item.toJson();
    expect(json['id'], 'i7');
    expect(json['evidence_quote'], 'я отправлю смету Ивану');
    expect(json['approved'], isTrue);
    expect(json['end_s'], 4.0);
  });

  test('без id в ответе сервера получается устойчивый запасной id', () {
    final a = Item.fromJson({'title': 'Позвонить', 'quote': 'позвони ему', 'start_s': 5});
    final b = Item.fromJson({'title': 'Позвонить', 'quote': 'позвони ему', 'start_s': 5});
    expect(a!.id, b!.id);
    expect(a.id, isNot(''));
  });

  test('участники читаются вместе с вердиктом', () {
    // Вердикт — это ответ на «чей голос»: без него экран не отличит своего от чужого.
    final d = Digest.fromJson(<String, dynamic>{
      'summary': <String>[],
      'decisions': <String>[],
      'open_questions': <String>[],
      'items': <dynamic>[],
      'participants': <dynamic>[
        <String, dynamic>{'speaker': 'S1', 'name': 'Анна', 'verdict': 'owner'},
        <String, dynamic>{'speaker': 'S2', 'name': 'Курьер', 'verdict': 'foreign'},
      ],
    });
    expect(d.participants.length, 2);
    expect(d.participants[0][0], 'Анна');
    expect(d.participants[1][1], 'foreign');
  });

  test('без участников список пуст, а не падает', () {
    final d = Digest.fromJson(<String, dynamic>{'summary': <String>[], 'items': <dynamic>[]});
    expect(d.participants, isEmpty);
  });

  test('признак частичного разбора доходит до экрана', () {
    final d = Digest.fromJson({
      'summary': ['Коротко'],
      'items': [],
      'participants': [],
      'truncated': true,
    });
    expect(d.truncated, isTrue);
  });

  test('обычный разбор не считается частичным', () {
    final d = Digest.fromJson({'summary': ['Коротко'], 'items': [], 'participants': []});
    expect(d.truncated, isFalse);
  });

  test('тема разговора доходит до экрана', () {
    final d = Digest.fromJson({'topic': 'Бюджет и сроки', 'summary': [], 'items': [], 'participants': []});
    expect(d.topic, 'Бюджет и сроки');
  });

  test('без темы экран не показывает пустой блок', () {
    final d = Digest.fromJson({'summary': [], 'items': [], 'participants': []});
    expect(d.topic, isEmpty);
  });

  test('неподтверждённые задачи доходят до человека причиной, а не служебным индексом', () {
    final d = Digest.fromJson({
      'summary': [],
      'items': [],
      'participants': [],
      'rejected': [
        {'index': 0, 'title': 'Позвонить в банк', 'reason': 'цитаты нет в расшифровке'},
        {'index': 1, 'title': '', 'reason': 'пустой заголовок'},
      ],
    });
    expect(d.rejected, ['Позвонить в банк — цитаты нет в расшифровке', 'пустой заголовок']);
  });

  test('без отсева строка не появляется', () {
    final d = Digest.fromJson({'summary': [], 'items': [], 'participants': []});
    expect(d.rejected, isEmpty);
  });

  group('срок показывается по-человечески', () {
    Item withDue(String due) =>
        Item(id: 'i', kind: 'reminder', title: 'Позвонить', owner: '', due: due, quote: 'Позвони мне завтра утром', startS: 0, approved: false);

    test('ISO-дата превращается в «27 ноя, 10:00»', () {
      expect(withDue('2026-11-27T10:00:00').dueHuman, '27 ноя, 10:00');
    });

    test('дата без времени — без ложного часа', () {
      expect(withDue('2026-11-27T00:00:00').dueHuman, '27 ноя');
    });

    test('непонятный срок отдаём как есть, а не выдумываем дату', () {
      expect(withDue('завтра утром').dueHuman, 'завтра утром');
    });
  });
}
