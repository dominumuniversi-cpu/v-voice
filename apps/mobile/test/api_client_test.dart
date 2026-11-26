import 'package:flutter_test/flutter_test.dart';
import 'package:v_voice/src/api_client.dart';

/// Транспорт-заглушка: отвечает тем, что велели, и запоминает путь.
class FakeTransport implements HttpTransport {
  FakeTransport(this.responses);

  final Map<String, (int, String)> responses;
  final List<String> calls = [];

  @override
  Future<(int, String)> post(String path, Map<String, dynamic> body) async {
    calls.add('POST ' + path);
    return responses[path] ?? (404, '{}');
  }

  @override
  Future<(int, String)> get(String path) async {
    calls.add('GET ' + path);
    return responses[path] ?? (404, '{}');
  }
}

void main() {
  group('проверка ключа', () {
    test('200 отдаёт вердикт и сообщение', () async {
      final c = ApiClient(transport: FakeTransport({'/api/v1/probe': (200, '{"verdict":"working","message":"Ключ рабочий"}')}), baseUrl: '');
      final (verdict, message) = await c.probe('deepgram', 'x' * 32);
      expect(verdict, 'working');
      expect(message, 'Ключ рабочий');
    });

    test('400 превращается в отказ с текстом сервера', () async {
      final c = ApiClient(transport: FakeTransport({'/api/v1/probe': (400, '{"message":"Укажите provider"}')}), baseUrl: '');
      final (verdict, message) = await c.probe('', '');
      expect(verdict, 'rejected');
      expect(message, 'Укажите provider');
    });

    test('прочие коды не выдают себя за успех', () async {
      final c = ApiClient(transport: FakeTransport({'/api/v1/probe': (500, 'boom')}), baseUrl: '');
      final (verdict, _) = await c.probe('deepgram', 'x' * 32);
      expect(verdict, 'rejected');
    });
  });

  group('проверка элемента', () {
    test('элемент с цитатой проходит', () async {
      final c = ApiClient(transport: FakeTransport({'/api/v1/items/validate': (200, '{"ok":true}')}), baseUrl: '');
      final (ok, _) = await c.validateItem({'title': 'x'}, 'text');
      expect(ok, isTrue);
    });

    test('422 возвращает причину отказа по-русски', () async {
      final c = ApiClient(transport: FakeTransport({'/api/v1/items/validate': (422, '{"reason":"цитаты нет в расшифровке"}')}), baseUrl: '');
      final (ok, reason) = await c.validateItem({'title': 'x'}, 'text');
      expect(ok, isFalse);
      expect(reason.contains('цитаты нет'), isTrue);
    });
  });

  group('разбор с сервера', () {
    test('корректный ответ даёт выжимку', () async {
      final body = '{"summary":["Обсудили смету"],"items":[{"title":"Отправить смету","quote":"я отправлю смету завтра","start_s":12}]}';
      final c = ApiClient(transport: FakeTransport({'/api/v1/sessions/s1/digest': (200, body)}), baseUrl: '');
      final d = await c.fetchDigest('s1');
      expect(d, isNotNull);
      expect(d!.summary.single, 'Обсудили смету');
      expect(d.items.single.timecode, '00:12');
    });

    test('ошибка сервера не превращается в пустую выжимку-обманку', () async {
      final c = ApiClient(transport: FakeTransport({'/api/v1/sessions/s1/digest': (500, 'oops')}), baseUrl: '');
      expect(await c.fetchDigest('s1'), isNull);
    });

    test('битый JSON не роняет приложение', () async {
      final c = ApiClient(transport: FakeTransport({'/api/v1/sessions/s1/digest': (200, 'не json')}), baseUrl: '');
      expect(await c.fetchDigest('s1'), isNull);
    });

    test('русский текст не портится', () async {
      final body = '{"summary":["Решили отправить счёт в среду"],"items":[]}';
      final c = ApiClient(transport: FakeTransport({'/api/v1/sessions/s1/digest': (200, body)}), baseUrl: '');
      final d = await c.fetchDigest('s1');
      expect(d!.summary.single, 'Решили отправить счёт в среду');
    });

    test('путь запроса собран правильно', () async {
      final t = FakeTransport({});
      final c = ApiClient(transport: t, baseUrl: '');
      await c.fetchDigest('abc');
      expect(t.calls.single, 'GET /api/v1/sessions/abc/digest');
    });
  });
  group('разбор: причина вместо молчания', () {
    const path = '/api/v1/sessions/abc/digest';

    test('404 от сервера даёт причину, а не пустоту', () async {
      final api = ApiClient(transport: FakeTransport({
        path: (404, '{"error":"digest_not_found","message":"Разбор этой записи ещё не готов."}'),
      }), baseUrl: '');
      expect(await api.fetchDigest('abc'), isNull);
      expect(api.lastDigestProblem, contains('ещё не готов'));
    });

    test('ответ без текста причины не остаётся пустым', () async {
      final api = ApiClient(transport: FakeTransport({path: (500, '')}), baseUrl: '');
      expect(await api.fetchDigest('abc'), isNull);
      expect(api.lastDigestProblem, contains('500'));
    });

    test('успех не оставляет ложной причины', () async {
      final api = ApiClient(transport: FakeTransport({
        path: (200, '{"summary":"итог","items":[]}'),
      }), baseUrl: '');
      await api.fetchDigest('abc');
      expect(api.lastDigestProblem, isEmpty);
    });
  });

}
