import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:v_voice/src/level_meter.dart';

void main() {
  testWidgets('тишина объясняется словами, а не пустой полоской', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: Scaffold(body: LevelMeter(level: 0))));
    final semantics = tester.getSemantics(find.byType(LevelMeter));
    expect(semantics.label, contains('тихо'));
  });

  testWidgets('громкий звук назван числом из 100', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: Scaffold(body: LevelMeter(level: 0.5))));
    final semantics = tester.getSemantics(find.byType(LevelMeter));
    expect(semantics.label, contains('50 из 100'));
  });

  testWidgets('мусорное значение не ломает рисунок', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: Scaffold(body: LevelMeter(level: double.nan))));
    expect(tester.takeException(), isNull);
  });
}
