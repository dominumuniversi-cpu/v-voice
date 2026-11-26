import 'package:flutter/material.dart';

import 'server_settings.dart';
import 'theme.dart';

/// Первый запуск: человек выбирает адрес сервера.
///
/// Почему это отдельный экран, а не «настройки в глубине»: без адреса приложение не работает вовсе.
/// Раньше оно молча стучалось в выдуманный домен, показывало «сервер не ответил», и человек
/// решал, что приложение сломано, — хотя ему просто нужно было указать адрес.
class FirstRunScreen extends StatefulWidget {
  const FirstRunScreen({super.key, required this.onSaved});

  /// Сохраняет выбранный адрес и продолжает запуск.
  final Future<void> Function(String) onSaved;

  @override
  State<FirstRunScreen> createState() => _FirstRunScreenState();
}

class _FirstRunScreenState extends State<FirstRunScreen> {
  final _field = TextEditingController();
  String? _problem;
  bool _busy = false;

  @override
  void dispose() {
    _field.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final raw = _field.text.trim();
    final problem = ServerSettings.problem(raw);
    if (problem != null) {
      setState(() => _problem = problem);
      return;
    }
    setState(() {
      _busy = true;
      _problem = null;
    });
    await widget.onSaved(raw);
    if (mounted) setState(() => _busy = false);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: VVTheme.bg,
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(24),
          children: [
            const SizedBox(height: 32),
            const Text('Умный диктофон', style: TextStyle(fontSize: 26, fontWeight: FontWeight.w700, color: VVTheme.ink)),
            const SizedBox(height: 10),
            const Text(
              'Чтобы слушать и понимать разговор, приложению нужен адрес сервера, который этим занимается. '
              'Спросите владельца сервера, если адреса нет.',
              style: TextStyle(fontSize: 15, height: 1.45, color: VVTheme.inkMuted),
            ),
            const SizedBox(height: 28),
            TextField(
              controller: _field,
              keyboardType: TextInputType.url,
              decoration: const InputDecoration(hintText: 'v-voice.ru или 192.168.8.49:8000', isDense: true),
              onSubmitted: (_) => _submit(),
            ),
            if (_problem != null) ...[
              const SizedBox(height: 10),
              Text(_problem!, style: const TextStyle(fontSize: 13, color: VVTheme.warn)),
            ],
            const SizedBox(height: 16),
            FilledButton(
              onPressed: _busy ? null : _submit,
              child: Text(_busy ? 'Проверяю…' : 'Продолжить'),
            ),
            const SizedBox(height: 28),
            const Text('Готовые адреса', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: VVTheme.ink)),
            const SizedBox(height: 8),
            for (final preset in ServerSettings.presets)
              ListTile(
                contentPadding: EdgeInsets.zero,
                title: Text(preset, style: const TextStyle(fontSize: 14, color: VVTheme.ink)),
                trailing: const Icon(Icons.chevron_right, color: VVTheme.inkMuted),
                onTap: () {
                  _field.text = preset;
                  _submit();
                },
              ),
          ],
        ),
      ),
    );
  }
}
