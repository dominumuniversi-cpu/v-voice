import 'package:flutter_test/flutter_test.dart';
import 'package:v_voice/src/session_model.dart';

void main() {
  group('время записи', () {
    test('счётчик тикает только при записи', () {
      final s = SessionModel();
      s.tick(recording: true);
      s.tick(recording: true);
      s.tick(recording: false);
      expect(s.seconds, 2);
      expect(s.clock, '00:02');
    });

    test('часы появляются только после часа', () {
      final s = SessionModel()..seconds = 59;
      expect(s.clock, '00:59');
      s.seconds = 61;
      expect(s.clock, '01:01');
      s.seconds = 3725;
      expect(s.clock, '1:02:05');
    });
  });

  group('метки моментов', () {
    test('метка запоминает текущее время, а не сдвигается потом', () {
      final s = SessionModel()..seconds = 125;
      final first = s.mark();
      s.seconds = 30;
      final second = s.mark();
      expect(first.clock, '02:05');
      expect(first.atSeconds, 125);
      expect(second.clock, '00:30');
      expect(s.marks.length, 2);
    });

    test('метки нумеруются по порядку', () {
      final s = SessionModel();
      expect(s.mark().index, 1);
      expect(s.mark().index, 2);
    });
  });

  group('уровень сигнала', () {
    test('ноль — тишина, а не «тихо»', () {
      expect(SessionModel(level: 0).levelState, 'тишина');
    });

    test('уровни подписаны по-человечески', () {
      expect(SessionModel(level: 0.1).levelState, 'тихо');
      expect(SessionModel(level: 0.5).levelState, 'нормально');
      expect(SessionModel(level: 0.95).levelState, 'слишком громко');
    });
  });

  group('подсказки', () {
    test('без проблем подсказок нет', () {
      expect(SessionModel(level: 0.5).hint, isNull);
    });

    test('предупреждение системы показывается первым', () {
      final s = SessionModel(level: 0.5)..alerted = true;
      expect(s.hint!, contains('помехах'));
    });

    test('пропавший звук после метки замечается', () {
      final s = SessionModel(level: 0.0);
      s.mark();
      expect(s.hint!, contains('звук пропал'));
    });
  });
}
