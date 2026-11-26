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

    test('слэш в конце не считается ошибкой — он нормализуется', () {
      expect(ServerSettings.problem('https://v-voice.ru/'), isNull);
      expect(ServerSettings.normalize('https://v-voice.ru/'), 'https://v-voice.ru');
    });

    test('мусор в домене ловится', () {
      expect(ServerSettings.problem('https://')!, contains('домен'));
    });

    test('запрос и якорь недопустимы', () {
      expect(ServerSettings.problem('https://v.ru?x=1')!, contains('?'));
    });

    test('адрес с завершающим слэшем сохраняется и потом читается', () {
      expect(ServerSettings.problem('https://v-voice.ru/'), isNull);
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

  test('внешний http-адрес предупреждает о шифровании', () {
    expect(ServerSettings.insecureNote('http://192.168.8.49/vvoice'), isNotNull);
  });

  test('https не пугает зря', () {
    expect(ServerSettings.insecureNote('https://v-voice.example.ru'), isNull);
  });

  test('свой компьютер по http — нормально', () {
    expect(ServerSettings.insecureNote('http://127.0.0.1:8900'), isNull);
    expect(ServerSettings.insecureNote('http://localhost:8900'), isNull);
  });
}
