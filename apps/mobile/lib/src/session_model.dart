/// Состояние экрана записи (FR-4) и метки моментов (FR-5).
///
/// Почему вынесено из виджета: всё, что здесь считается, человек читает как факт
/// («идёт 12:34», «двое голосов», «уровень хороший»). Если это врёт, человек теряет доверие
/// к записи и выключает её в середине встречи. Поэтому у каждого правила есть тест.
class SessionModel {
  SessionModel({this.voices = 0, this.level = 0.0});

  int seconds = 0;
  int voices;
  double level; // 0.0 .. 1.0 — текущий уровень сигнала
  bool alerted = false; // телефон предупредил, что запись может идти с помехами
  final List<Mark> marks = [];

  /// Время как 12:34 или 1:02:03 — часы появляются только после часа, чтобы не рябило.
  String get clock {
    final h = seconds ~/ 3600;
    final m = (seconds % 3600) ~/ 60;
    final s = seconds % 60;
    final mm = m.toString().padLeft(2, '0');
    final ss = s.toString().padLeft(2, '0');
    return h > 0 ? h.toString() + ':' + mm + ':' + ss : mm + ':' + ss;
  }

  /// Считаем время только когда действительно идёт запись: на паузе счётчик стоит.
  void tick({required bool recording}) {
    if (recording) seconds += 1;
  }

  /// Метка ставится в момент нажатия и не сдвигается, даже если запись продолжается.
  Mark mark() {
    final m = Mark(atSeconds: seconds, index: marks.length + 1);
    marks.add(m);
    return m;
  }

  /// Уровень: человеку нужно не число, а «слышно / тихо».
  String get levelState {
    if (level <= 0.02) return 'тишина';
    if (level < 0.15) return 'тихо';
    if (level < 0.85) return 'нормально';
    return 'слишком громко';
  }

  /// Подсказка, если человек говорит в микрофон издалека или микрофон закрыт рукой.
  String? get hint {
    if (alerted) return 'Телефон сообщил о помехах — проверьте, не закрыт ли микрофон.';
    if (marks.isNotEmpty && level <= 0.02) return 'Похоже, звук пропал: уровень упал до нуля.';
    return null;
  }
}

class Mark {
  Mark({required this.atSeconds, required this.index});

  final int atSeconds;
  final int index;

  /// 05:12 — по этой метке человек потом находит место в записи.
  String get clock {
    final m = (atSeconds ~/ 60).toString().padLeft(2, '0');
    final s = (atSeconds % 60).toString().padLeft(2, '0');
    return m + ':' + s;
  }
}
