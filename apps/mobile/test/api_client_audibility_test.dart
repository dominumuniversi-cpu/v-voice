import 'package:flutter_test/flutter_test.dart';

import 'package:v_voice/src/api_client.dart';

/// Кусок PCM16 из амплитуды: удобно задавать «громкость» тестом, а не байтами.
List<int> pcm(double amplitude, int samples) {
  final out = <int>[];
  for (var i = 0; i < samples; i++) {
    final v = (amplitude * 32767 * (i.isEven ? 1 : 1)).round();
    out.add(v & 0xFF);
    out.add((v >> 8) & 0xFF);
  }
  return out;
}

void main() {
  group('отправка только слышимого звука', () {
    test('тишина не уходит в сеть', () {
      final api = ApiClient(transport: _NeverCalled(), baseUrl: 'https://x');
      expect(api.isAudible(pcm(0, 1600)), isFalse);
    });

    test('гул комнаты тише порога', () {
      final api = ApiClient(transport: _NeverCalled(), baseUrl: 'https://x');
      expect(api.isAudible(pcm(0.004, 1600)), isFalse);
    });

    test('речь уходит', () {
      final api = ApiClient(transport: _NeverCalled(), baseUrl: 'https://x');
      expect(api.isAudible(pcm(0.2, 1600)), isTrue);
    });

    test('громкость считается по настоящим байтам PCM16', () {
      // Полная шкала: все отсчёты 32767 — RMS почти 1.0.
      expect(ApiClient.rmsOf(pcm(1.0, 100)), closeTo(1.0, 0.01));
      // Половина шкалы — примерно 0.5.
      expect(ApiClient.rmsOf(pcm(0.5, 100)), closeTo(0.5, 0.02));
    });
  });

  group('режим «только участники» уходит на сервер', () {
    test('по умолчанию флаг не отправляется', () async {
      final transport = _Recorder();
      final api = ApiClient(transport);
      await api.startAnalysis('s1');
      expect(transport.lastBody, isEmpty);
    });

    test('включённый режим отправляет members_only: true', () async {
      final transport = _Recorder();
      final api = ApiClient(transport)..membersOnly = true;
      await api.startAnalysis('s1');
      expect(transport.lastBody?['members_only'], true);
    });
  });
}

class _Recorder implements HttpTransport {
  Map<String, dynamic>? lastBody;

  @override
  Future<(int, String)> get(String path, {Map<String, String>? headers}) async => (200, '{}');

  @override
  Future<(int, String)> post(String path, Map<String, dynamic> body, {Map<String, String>? headers}) async {
    lastBody = body;
    return (200, '{}');
  }
}

class _NeverCalled implements HttpTransport {
  @override
  Future<(int, String)> get(String path, {Map<String, String>? headers}) async => (200, '{}');

  @override
  Future<(int, String)> post(String path, Map<String, dynamic> body, {Map<String, String>? headers}) async =>
      (200, '{}');
}
