import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:v_voice/src/api_client.dart';
import 'package:v_voice/src/digest_model.dart';
import 'package:v_voice/src/digest_screen.dart';

/// Транспорт, который отвечает «отправлено» — и считает, сколько раз его позвали.
class _Fake implements HttpTransport {
  int posts = 0;

  @override
  Future<(int, String)> get(String path, {Map<String, String>? headers}) async =>
      (200, '{"text": "", "segments": []}');

  @override
  Future<(int, String)> post(String path, Map<String, dynamic> body,
      {Map<String, String>? headers}) async {
    if (path.contains('/export')) {
      posts++;
      return (200, '{"sent": 1, "failed": 0, "skipped": 0, "results": []}');
    }
    return (200, '{}');
  }
}

void main() {
  testWidgets('после успешной отправки второй раз отправить нельзя', (tester) async {
    final transport = _Fake();
    final api = ApiClient(transport: transport, baseUrl: '');
    final digest = Digest.fromJson({
      'summary': ['Обсудили смету'],
      'items': [
        {'kind': 'task', 'title': 'Отправить смету', 'quote': 'я отправлю смету завтра'},
      ],
    });

    await tester.pumpWidget(MaterialApp(
      home: DigestScreen(digest: digest, api: api, sessionId: 'abc123'),
    ));
    await tester.pumpAndSettle();

    // Отправлять можно только принятое человеком — это правило проекта, а не помеха тесту.
    await tester.tap(find.text('Принять'));
    await tester.pumpAndSettle();

    final send = find.text('Отправить в задачник');
    expect(send, findsOneWidget);
    await tester.tap(send);
    await tester.pumpAndSettle();

    // Первая отправка ушла ровно один раз, и кнопка теперь говорит «уже отправлено».
    expect(transport.posts, 1);
    expect(find.textContaining('Уже отправлено'), findsOneWidget);
    expect(find.text('Отправить в задачник'), findsNothing);
  });
}
