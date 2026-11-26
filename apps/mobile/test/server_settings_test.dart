import 'package:flutter_test/flutter_test.dart';
import 'package:v_voice/src/server_settings.dart';

void main() {
  group('адрес сервера', () {
    test('пустой адрес объясняется', () {
      expect(ServerSettings.problem('   ')!, contains('не заполнен'));
    });

    test('без схемы — понятная ошибка', () {
      expect(ServerSettings.problem('v-voice.ru')!, contains('http://'));
    });

    test('слэш в конце — отдельная подсказка', () {
      expect(ServerSettings.problem('https://v-voice.ru/')!, contains('слэш'));
    });

    test('мусор в домене ловится', () {
      expect(ServerSettings.problem('https://')!, contains('домен'));
    });

    test('запрос и якорь недопустимы', () {
      expect(ServerSettings.problem('https://v.ru?x=1')!, contains('?'));
    });

    test('нормальный адрес проходит', () {
      expect(ServerSettings.problem('https://v-voice.ru'), isNull);
      expect(ServerSettings.problem('http://127.0.0.1:8900'), isNull);
    });

    test('нормализация убирает лишние слэши', () {
      expect(ServerSettings.normalize('https://v.ru//'), 'https://v.ru');
      expect(ServerSettings.normalize(' https://v.ru '), 'https://v.ru');
    });

    test('есть готовые адреса для быстрого выбора', () {
      expect(ServerSettings.presets.length, greaterThanOrEqualTo(2));
      expect(ServerSettings.presets.first.startsWith('https://'), isTrue);
    });
  });
}
