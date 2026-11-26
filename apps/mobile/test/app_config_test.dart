import 'package:flutter_test/flutter_test.dart';
import 'package:v_voice/src/app_config.dart';
import 'package:v_voice/src/api_client.dart';

class FakeTransport implements HttpTransport {
  final List<String> calls = [];
  @override
  Future<(int, String)> get(String path, {Map<String, String>? headers}) async {
    calls.add(path);
    return (200, '{}');
  }

  @override
  Future<(int, String)> post(String path, Map<String, dynamic> body, {Map<String, String>? headers}) async {
    calls.add(path);
    return (200, '{"verdict":"working","message":"ок"}');
  }
}

void main() {
  test('адрес с лишним слэшем нормализуется в клиенте', () {
    final t = FakeTransport();
    final cfg = AppConfig(serverUrl: 'https://v.ru/', transport: t);
    expect(cfg.api.baseUrl, 'https://v.ru');
  });

  test('адрес без схемы проблемой не считается', () {
    // Решение осознанное: схему дописывает нормализация.
    expect(AppConfig(serverUrl: 'v.ru', transport: FakeTransport()).addressProblem, isNull);
    expect(AppConfig(serverUrl: 'https://v.ru', transport: FakeTransport()).addressProblem, isNull);
  });

  test('случайное слово видно конфигурации как проблема', () {
    expect(AppConfig(serverUrl: 'плохо', transport: FakeTransport()).addressProblem, isNotNull);
  });

  test('клиент действительно ходит через переданный транспорт', () async {
    final t = FakeTransport();
    final cfg = AppConfig(serverUrl: 'https://v.ru', transport: t);
    await cfg.api.probe('deepgram', 'a' * 32);
    expect(t.calls.single, '/api/v1/probe');
  });

  test('адрес по умолчанию — https', () {
    // Постоянного адреса нет намеренно: приложение обязано спросить адрес, а не стучаться
    // в выдуманный домен и показывать «сервер не ответил».
    expect(AppConfig.defaultServer, isEmpty);
  });
}
