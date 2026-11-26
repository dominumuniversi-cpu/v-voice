import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:v_voice/src/api_client.dart';
import 'package:v_voice/src/digest_loader.dart';

class _Fake implements HttpTransport {
  _Fake(this.reply);
  final (int, String) reply;

  @override
  Future<(int, String)> get(String path) async => reply;

  @override
  Future<(int, String)> post(String path, Map<String, dynamic> body) async => reply;
}

void main() {
  testWidgets('без записи разбора нет и это сказано словами', (tester) async {
    final api = ApiClient(transport: _Fake((200, '{}')), baseUrl: '');
    await tester.pumpWidget(MaterialApp(home: DigestLoader(api: api)));
    await tester.pumpAndSettle();
    expect(find.textContaining('запись не отправлена'), findsOneWidget);
  });

  testWidgets('сервер без разбора даёт причину, а не пустоту', (tester) async {
    final api = ApiClient(
      transport: _Fake((404, '{"error":"digest_not_found","message":"Разбор этой записи ещё не готов."}')),
      baseUrl: '',
    );
    await tester.pumpWidget(MaterialApp(home: DigestLoader(api: api, sessionId: 's1')));
    await tester.pumpAndSettle();
    expect(find.textContaining('ещё не готов'), findsOneWidget);
    expect(find.text('Повторить'), findsOneWidget);
  });

  testWidgets('готовый разбор показывается на экране разбора', (tester) async {
    final api = ApiClient(
      transport: _Fake((200, '{"summary":["Обсудили смету"],"decisions":[],"open_questions":[],"items":[]}')),
      baseUrl: '',
    );
    await tester.pumpWidget(MaterialApp(home: DigestLoader(api: api, sessionId: 's1')));
    await tester.pumpAndSettle();
    expect(find.text('Разбор разговора'), findsOneWidget);
    expect(find.textContaining('Обсудили смету'), findsOneWidget);
  });
}
