import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vvoice/src/device_key_store.dart';
import 'package:vvoice/src/settings_screen.dart';

void main() {
  testWidgets('в настройках можно вписать ключ устройства', (tester) async {
    final store = MemoryDeviceKeyStore();
    await tester.pumpWidget(MaterialApp(home: SettingsScreen(deviceKeyStore: store)));
    await tester.pumpAndSettle();

    expect(find.text('Ключ устройства (если сервер с замком)'), findsOneWidget);

    await tester.enterText(find.widgetWithText(TextField, 'Ключ устройства (если сервер с замком)'), 'secret-key-123');
    await tester.tap(find.text('Сохранить').last);
    await tester.pumpAndSettle();

    expect(await store.read(), 'secret-key-123');
    expect(find.text('Ключ сохранён.'), findsOneWidget);
  });

  testWidgets('короткий ключ не сохраняется и объясняет почему', (tester) async {
    final store = MemoryDeviceKeyStore();
    await tester.pumpWidget(MaterialApp(home: SettingsScreen(deviceKeyStore: store, initialDeviceKey: '')));
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextField, 'Ключ устройства (если сервер с замком)'), 'abc');
    await tester.tap(find.text('Сохранить').last);
    await tester.pumpAndSettle();
    expect(await store.read(), isNull);
    expect(find.textContaining('слишком короткий'), findsOneWidget);
  });

  test('пустой ключ — законный случай', () {
    expect(deviceKeyProblem(''), isNull);
    expect(deviceKeyProblem('  '), isNull);
    expect(deviceKeyProblem('k' * 8), isNull);
    expect(deviceKeyProblem('k k k k k'), isNotNull);
  });
}
