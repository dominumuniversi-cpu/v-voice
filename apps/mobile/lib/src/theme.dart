import 'package:flutter/material.dart';

/// Тема приложения. Один источник цвета для экранов и для документа
/// docs/UI/tokens.css: светлые --vt-* переменные перенесены сюда значениями.
class VVTheme {
  static const Color bg = Color(0xFF0A0C10);
  static const Color surface = Color(0xFF11151D);
  static const Color accent = Color(0xFF5B8CFF);
  static const Color live = Color(0xFFFF4D6D);
  static const Color ok = Color(0xFF3DDC97);
  static const Color warn = Color(0xFFFFB020);

  /// Мягкое предупреждение: важное, но не блокирующее (например, «живая расшифровка не идёт»).
  static const Color warnSoft = Color(0xFFE0A030);
  static const Color ink = Color(0xFFE9EEF6);
  static const Color inkMuted = Color(0xFF8C97A8);

  static ThemeData dark() {
    return ThemeData(
      brightness: Brightness.dark,
      scaffoldBackgroundColor: bg,
      colorScheme: const ColorScheme.dark(primary: accent, surface: surface, error: warn),
      fontFamily: 'Inter',
      useMaterial3: true,
    );
  }
}
