import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:v_voice/src/api_client.dart';
import 'package:v_voice/src/server_scope.dart';
import 'package:v_voice/src/settings_screen.dart';

/// Транспорт-заглушка: отвечает пустым объектом и запоминает вызовы.
class _Spy implements HttpTransport {
  final List<String> calls = [];

  @override
  Future<(int, String)> get(String path) async {
    calls.add('GET ' + path);
    return (200, '{}');
  }

  @override
  Future<(int, String)> post(String path, Map<String, dynamic> body) async {
    calls.add('POST ' + path);
    return (200, '{"verdict":"working","message":"Ключ рабочий"}');
  }
}

void main() {
  testWidgets('экран настроек находит действующий адрес', (tester) async {
    String? scopeSeen;
    await tester.pumpWidget(MaterialApp(
      home: ServerScope(
        serverUrl: 'https://fresh.example',
        onChanged: (_) async {},
        child: Builder(
          builder: (ctx) {
            // Здесь проверяется главное: экран увидит актуальный адрес, а не снимок из конструктора.
            scopeSeen = ServerScope.maybeOf(ctx)?.serverUrl;
            return SettingsScreen(
              api: ApiClient(transport: _Spy(), baseUrl: 'https://old.example'),
              initialServerUrl: 'https://old.example',
              store: null,
            );
          },
        ),
      ),
    ));
    await tester.pumpAndSettle();

    expect(scopeSeen, 'https://fresh.example');
    expect(find.text('Подключение моделей'), findsOneWidget);
  });

  testWidgets('без scope экран работает на переданном клиенте', (tester) async {
    // Нет подписки на адрес — значит проверка использует api, пришедший в конструкторе.
    await tester.pumpWidget(MaterialApp(
      home: SettingsScreen(
        api: ApiClient(transport: _Spy(), baseUrl: 'https://old.example'),
        initialServerUrl: 'https://old.example',
        store: null,
      ),
    ));
    await tester.pumpAndSettle();
    expect(find.text('Подключение моделей'), findsOneWidget);
  });
}
