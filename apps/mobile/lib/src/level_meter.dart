import 'package:flutter/material.dart';

import 'theme.dart';

/// Уровень сигнала микрофона: полоска, которая видна всё время записи.
///
/// Зачем: натив считает RMS и присылает его, но на экране его не было — человек узнавал,
/// что его не слышно, только по пустой расшифровке через полчаса. Тихий сигнал честно
/// бледнеет, а не выглядит так же, как громкий.
class LevelMeter extends StatelessWidget {
  const LevelMeter({super.key, required this.level, this.width = 64});

  /// 0..1 — доля от полной шкалы. За пределами диапазона обрезается, а не ломает рисунок.
  final double level;
  final double width;

  @override
  Widget build(BuildContext context) {
    final value = level.isFinite ? level.clamp(0.0, 1.0).toDouble() : 0.0;
    // Ниже 0.02 человек реально молчит или микрофон далеко: показываем «молчим», а не «слушаем».
    final silent = value < 0.02;
    final filled = (value * width).clamp(2.0, width).toDouble();
    return Semantics(
      label: silent ? 'Уровень сигнала: тихо' : 'Уровень сигнала: ' + (value * 100).round().toString() + ' из 100',
      child: Container(
        width: width,
        height: 6,
        decoration: BoxDecoration(color: VVTheme.warnSoft, borderRadius: BorderRadius.circular(3)),
        alignment: Alignment.centerLeft,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 120),
          width: silent ? 2 : filled,
          height: 6,
          decoration: BoxDecoration(
            color: silent ? VVTheme.inkMuted : VVTheme.live,
            borderRadius: BorderRadius.circular(3),
          ),
        ),
      ),
    );
  }
}
