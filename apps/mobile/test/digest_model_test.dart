import 'package:flutter_test/flutter_test.dart';
import 'package:v_voice/src/digest_model.dart';

void main() {
  group('Digest.fromJson', () {
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
}
