import 'package:flutter_test/flutter_test.dart';
import 'package:v_voice/src/providers_model.dart';

void main() {
  group('каталог провайдеров', () {
    test('есть провайдеры обоих видов', () {
      expect(KeyCheck.hasKind('asr'), isTrue);
      expect(KeyCheck.hasKind('llm'), isTrue);
    });

    test('у каждого провайдера есть человеческая подпись', () {
      for (final p in kProviders) {
        expect(p.title.isNotEmpty, isTrue, reason: p.id);
        expect(p.note.length, greaterThan(20), reason: p.id);
      }
    });

    test('локальные провайдеры не просят ключ', () {
      final local = kProviders.where((p) => p.id == 'gigaam' || p.id == 'ollama').toList();
      expect(local.length, 2);
      expect(local.every((p) => !p.needsKey), isTrue);
    });

    test('три пресета и у каждого есть подсказка', () {
      expect(kPresets.length, 3);
      for (final p in kPresets.values) {
        expect(p['title'], isNotNull);
        expect(p['hint'], isNotNull);
        expect(p['asr'], isNotNull);
        expect(p['llm'], isNotNull);
      }
    });

    test('пресет «приватно» ведёт на локальные модели', () {
      final p = kPresets['приватно']!;
      expect(p['asr'], 'gigaam');
      expect(p['llm'], 'ollama');
    });
  });

  group('проверка ключа', () {
    test('пустой ключ не проходит', () {
      expect(KeyCheck.problem('deepgram', '   '), 'Ключ не введён.');
    });

    test('ключ с пробелом не проходит', () {
      expect(KeyCheck.problem('deepgram', 'abcd efgh ijkl mnop')!.contains('пробел'), isTrue);
    });

    test('обрезанный ключ не проходит', () {
      expect(KeyCheck.problem('deepgram', 'abc')!.contains('слишком короткий'), isTrue);
    });

    test('нормальный ключ проходит', () {
      expect(KeyCheck.problem('deepgram', 'a' * 32), isNull);
    });

    test('локальному провайдеру ключ не нужен', () {
      expect(KeyCheck.problem('gigaam', ''), isNull);
      expect(KeyCheck.problem('ollama', ''), isNull);
    });

    test('неизвестный провайдер назван в ошибке', () {
      expect(KeyCheck.problem('openai', 'a' * 32)!.contains('openai'), isTrue);
    });
  });
}
