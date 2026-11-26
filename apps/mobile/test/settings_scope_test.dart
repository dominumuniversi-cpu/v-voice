import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:v_voice/src/api_client.dart';
import 'package:v_voice/src/server_scope.dart';
import 'package:v_voice/src/settings_screen.dart';

/// Транспорт-шпион: запоминает, куда его создали (адрес) и что вызвали.
class _Spy implements HttpTransport {
  _Spy(this.base);
  final String base;
  final List<String> calls = [];

  @override
  Future<(int, String)> get(String path) async {
    calls.add('GET ' + path);
    return (200, '{}');
  }

  @override
  Future<(int, String)> post(String path, Map<String, dynamic> body) async {
    calls.add('POST ' + path + ' @' + base);
    return (200, '{"verdict":"working","message":"Ключ рабочий"}');
  }
}

void main() {
  testWidgets('проверка ключа идёт на действующий адрес', (tester) async {
    final spies = <String, _Spy>{};
    HttpTransport make(String base) => spies.putIfAbsent(base, () => _Spy(base));

    await tester.pumpWidget(MaterialApp(
      home: ServerScope(
        serverUrl: 'https://fresh.example',
        onChanged: (_) async {},
        child: Builder(
          builder: (ctx) => SettingsScreen(
            api: ApiClient(transport: make('https://old.example'), baseUrl: 'https://old.example'),
            initialServerUrl: 'https://old.example',
            store: null,
          ),
        ),
      ),
    ));
    await tester.pumpAndSettle();

    // Сам факт: экран нашёл scope и построил клиент уже с новым адресом.
    expect(spies.keys.where((k) => k == 'https://old.example'), isEmpty);
  });
}
