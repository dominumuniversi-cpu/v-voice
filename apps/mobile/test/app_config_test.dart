import 'package:flutter_test/flutter_test.dart';
import 'package:v_voice/src/app_config.dart';
import 'package:v_voice/src/api_client.dart';

class FakeTransport implements HttpTransport {
  final List<String> calls = [];
  @override
  Future<(int, String)> get(String path) async {
    calls.add(path);
    return (200, '{}');
  }

  @override
  Future<(int, String)> post(String path, Map<String, dynamic> body) async {
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

  test('проблемный адрес виден конфигурации', () {
    expect(AppConfig(serverUrl: 'v.ru', transport: FakeTransport()).addressProblem, isNotNull);
    expect(AppConfig(serverUrl: 'https://v.ru', transport: FakeTransport()).addressProblem, isNull);
  });

  test('клиент действительно ходит через переданный транспорт', () async {
    final t = FakeTransport();
    final cfg = AppConfig(serverUrl: 'https://v.ru', transport: t);
    await cfg.api.probe('deepgram', 'a' * 32);
    expect(t.calls.single, '/api/v1/probe');
  });

  test('адрес по умолчанию — https', () {
    expect(AppConfig.defaultServer.startsWith('https://'), isTrue);
  });
}
