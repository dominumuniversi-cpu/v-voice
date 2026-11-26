import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:v_voice/src/recovered_screen.dart';

void main() {
  testWidgets('пустой список объясняет, почему тут пусто', (tester) async {
    await tester.pumpWidget(MaterialApp(home: RecoveredScreen(recordings: const [], onOpen: (_) {}, onDelete: (_) {})));
    expect(find.textContaining('Записей нет'), findsOneWidget);
  });

  testWidgets('запись показывает время, размер и две кнопки', (tester) async {
    final opened = <String>[];
    await tester.pumpWidget(MaterialApp(
      home: RecoveredScreen(
        recordings: const [
          {'path': '/tmp/a.wav', 'name': 'a.wav', 'bytes': 48000, 'modified_ms': 0},
        ],
        onOpen: opened.add,
        onDelete: (_) {},
      ),
    ));
    expect(find.textContaining('КБ'), findsOneWidget);
    expect(find.text('Разобрать'), findsOneWidget);
    expect(find.text('Удалить'), findsOneWidget);
    await tester.tap(find.text('Разобрать'));
    expect(opened, ['/tmp/a.wav']);
  });

  testWidgets('пустой путь не даёт нажать: нажимать нечего', (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: RecoveredScreen(
        recordings: const [
          {'path': '', 'name': 'a.wav', 'bytes': 48000, 'modified_ms': 0},
        ],
        onOpen: (_) {},
        onDelete: (_) {},
      ),
    ));
    final button = tester.widget<FilledButton>(find.byType(FilledButton));
    expect(button.onPressed, isNull);
  });
}
