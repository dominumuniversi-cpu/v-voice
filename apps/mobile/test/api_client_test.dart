import 'package:flutter_test/flutter_test.dart';
import 'package:v_voice/src/api_client.dart';
import 'package:v_voice/src/digest_model.dart';

/// Транспорт-заглушка: отвечает тем, что велели, и запоминает путь.
class FakeTransport implements HttpTransport {
  FakeTransport(this.responses);

  final Map<String, (int, String)> responses;
  final List<String> calls = [];

  @override
  Future<(int, String)> post(String path, Map<String, dynamic> body, {Map<String, String>? headers}) async {
    calls.add('POST ' + path);
    return responses[path] ?? (404, '{}');
  }

  @override
  Future<(int, String)> get(String path, {Map<String, String>? headers}) async {
    calls.add('GET ' + path);
    return responses[path] ?? (404, '{}');
  }
}

void main() {
  group('токен устройства', () {
    test('уходит заголовком Authorization', () async {
      final tr = RecordingTransport();
      final c = ApiClient(transport: tr, baseUrl: '', deviceToken: 'secret-1');
      await c.fetchHealth();
      expect(tr.lastHeaders?['Authorization'], 'Bearer secret-1');
    });

    test('без токена заголовка нет — открытый сервер остаётся открытым', () async {
      final tr = RecordingTransport();
      final c = ApiClient(transport: tr, baseUrl: '');
      await c.fetchHealth();
      expect(tr.lastHeaders, isNull);
    });
  });

  group('форма ответа разбора', () {
    test('вложенный разбор разворачивается', () async {
      final c = ApiClient(transport: FakeTransport({
        '/api/v1/sessions/s1/digest': (
          200,
          '{"live_text":"","digest":{"summary":["Обсудили смету"],"decisions":[],"open_questions":[],"items":[]}}'
        ),
      }), baseUrl: '');
      final d = await c.fetchDigest('s1');
      expect(d, isNotNull);
      expect(d!.summary.first, 'Обсудили смету');
    });

    test('плоский разбор читается как есть', () async {
      final c = ApiClient(transport: FakeTransport({
        '/api/v1/sessions/s1/digest': (200, '{"summary":["Пришли к смете"],"decisions":[],"open_questions":[],"items":[]}'),
      }), baseUrl: '');
      final d = await c.fetchDigest('s1');
      expect(d!.summary.first, 'Пришли к смете');
    });
  });

  group('отправка в задачник', () {
    test('задачи без цитаты не теряются молча', () async {
      final c = ApiClient(transport: FakeTransport({
        '/api/v1/sessions/s1/export': (
          200,
          '{"sent":1,"failed":0,"skipped":2,"results":[]}'
        ),
      }), baseUrl: '');
      final items = [Item(id: 'i1', kind: 'task', title: 'Отправить смету', owner: '', due: '', quote: 'я отправлю смету', startS: 1, endS: 3, approved: true)];
      final result = await c.exportItems('s1', items, {'helper': ''});
      expect(result.sent, 1);
      expect(result.skipped, 2);
      // Человек обязан узнать, что две одобренные задачи не ушли и почему.
      expect(result.problem, contains('без цитаты'));
    });

    test('без потерь сообщать нечего', () async {
      final c = ApiClient(transport: FakeTransport({
        '/api/v1/sessions/s1/export': (200, '{"sent":3,"failed":0,"skipped":0}'),
      }), baseUrl: '');
      final items = [Item(id: 'i1', kind: 'task', title: 'x', owner: '', due: '', quote: 'цитата из разговора', startS: 1, endS: 2, approved: true)];
      final result = await c.exportItems('s1', items, {'helper': ''});
      expect(result.problem, isEmpty);
    });
  });

  group('потерянные куски звука', () {
    test('успешная отправка не считает потерь', () async {
      final c = ApiClient(transport: FakeTransport({
        '/api/v1/sessions/s1/stream': (200, '{"text":"привет"}'),
      }), baseUrl: '');
      final text = await c.sendLiveChunk('s1', [1, 2, 3]);
      expect(text, 'привет');
      expect(c.chunksLost, 0);
    });

    test('отказ сервера объясняется и не выдаёт себя за текст', () async {
      final c = ApiClient(transport: FakeTransport({}), baseUrl: '');
      final text = await c.sendLiveChunk('s1', [1, 2, 3]);
      expect(text, isNull);
      expect(c.lastLiveProblem, contains('404'));
    });

    test('пустой кусок не отправляется вовсе', () async {
      final c = ApiClient(transport: FakeTransport({}), baseUrl: '');
      await c.sendLiveChunk('s1', const []);
      expect(c.chunksLost, 0);
    });
  });

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


/// Транспорт, который запоминает заголовки: так проверяется, что токен действительно уходит.
class RecordingTransport implements HttpTransport {
  Map<String, String>? lastHeaders;

  @override
  Future<(int, String)> get(String path, {Map<String, String>? headers}) async {
    lastHeaders = headers;
    return (200, '{}');
  }

  @override
  Future<(int, String)> post(String path, Map<String, dynamic> body, {Map<String, String>? headers}) async {
    lastHeaders = headers;
    return (200, '{}');
  }
}
