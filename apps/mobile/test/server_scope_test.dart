import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:v_voice/src/app_config.dart';
import 'package:v_voice/src/server_scope.dart';
import 'package:v_voice/src/server_settings.dart';
import 'package:v_voice/src/server_store.dart';

void main() {
  testWidgets('сохранённый адрес поднимается при старте', (tester) async {
    final store = MemoryServerStore('https://my.example');
    String? seen;
    await tester.pumpWidget(MaterialApp(
      home: ServerScopeLoader(
        store: store,
        child: (ctx) {
          seen = ServerScope.maybeOf(ctx)?.serverUrl;
          return const SizedBox();
        },
      ),
    ));
    await tester.pumpAndSettle();
    expect(seen, 'https://my.example');
  });

  testWidgets('без сохранения действует адрес по умолчанию', (tester) async {
    String? seen;
    await tester.pumpWidget(MaterialApp(
      home: ServerScopeLoader(
        store: MemoryServerStore(),
        child: (ctx) {
          seen = ServerScope.maybeOf(ctx)?.serverUrl;
          return const SizedBox();
        },
      ),
    ));
    await tester.pumpAndSettle();
    expect(seen, AppConfig.defaultServer);
  });

  testWidgets('смена адреса применяется и перерисовывает экраны', (tester) async {
    final store = MemoryServerStore();
    late ServerScope scope;
    await tester.pumpWidget(MaterialApp(
      home: ServerScopeLoader(
        store: store,
        child: (ctx) {
          scope = ServerScope.maybeOf(ctx)!;
          return const SizedBox();
        },
      ),
    ));
    await tester.pumpAndSettle();
    final before = scope.serverUrl;
    await scope.onChanged('https://other.example');
    await tester.pumpAndSettle();
    expect(scope.serverUrl, 'https://other.example');
    expect(before, isNot(scope.serverUrl));
    expect(await store.read(), 'https://other.example');
  });

  test('адрес со слэшем в конце нормализуется для запросов', () async {
    final store = MemoryServerStore();
    await ServerSettingsKeeper(store: store, validate: ServerSettings.problem, normalize: ServerSettings.normalize)
        .save('https://a.example/');
    expect(await store.read(), 'https://a.example');
  });
}
