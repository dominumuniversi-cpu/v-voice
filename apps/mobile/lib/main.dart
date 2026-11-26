import 'package:flutter/material.dart';

import 'src/method_channel_bridge.dart';
import 'src/recording_controller.dart';
import 'src/theme.dart';

/// Точка входа. Экран один: «Слушаю» -> живой текст -> выжимка и задачи.
void main() => runApp(const VoiceApp());

class VoiceApp extends StatelessWidget {
  const VoiceApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Умный диктофон',
      debugShowCheckedModeBanner: false,
      theme: VVTheme.dark(),
      home: ListenScreen(controller: RecordingController(MethodChannelBridge())),
    );
  }
}

/// Главный экран. Правило интерфейса проекта: одна главная кнопка, индикатор записи
/// постоянно на виду, никаких подтверждений перед остановкой.
class ListenScreen extends StatefulWidget {
  const ListenScreen({super.key, required this.controller});

  final RecordingController controller;

  @override
  State<ListenScreen> createState() => _ListenScreenState();
}

class _ListenScreenState extends State<ListenScreen> {
  @override
  void initState() {
    super.initState();
    widget.controller.bind();
    widget.controller.changes.listen((_) {
      if (mounted) setState(() {});
    });
  }

  @override
  void dispose() {
    widget.controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final c = widget.controller;
    final recording = c.state == RecordingState.recording;

    return Scaffold(
      backgroundColor: VVTheme.bg,
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  const Text('Умный диктофон', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w600)),
                  const Spacer(),
                  // Индикатор записи обязателен и виден всегда (правило UI-канона).
                  RecordingDot(active: recording),
                ],
              ),
              const SizedBox(height: 24),
              Expanded(
                child: SingleChildScrollView(
                  child: Text(
                    c.liveText.isEmpty ? 'Пока тихо. Нажмите «Слушаю» — я начну расшифровывать.' : c.liveText,
                    style: TextStyle(fontSize: 16, height: 1.5, color: c.liveText.isEmpty ? VVTheme.inkMuted : VVTheme.ink),
                  ),
                ),
              ),
              if (c.lastError.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(bottom: 16),
                  child: Text(c.lastError, style: const TextStyle(color: VVTheme.warn, fontSize: 14)),
                ),
              // Одна главная кнопка: действие зависит от состояния, без второй «кнопки отмены».
              SizedBox(
                height: 64,
                child: FilledButton(
                  style: FilledButton.styleFrom(backgroundColor: recording ? VVTheme.live : VVTheme.accent),
                  onPressed: recording ? c.stop : c.start,
                  child: Text(recording ? 'Стоп' : 'Слушаю', style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600)),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Точка-индикатор уровня (пульсация уровня сигнала в концепции «Signal»).
class RecordingDot extends StatelessWidget {
  const RecordingDot({super.key, required this.active});

  final bool active;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 10,
          height: 10,
          decoration: BoxDecoration(color: active ? VVTheme.live : VVTheme.inkMuted, shape: BoxShape.circle),
        ),
        const SizedBox(width: 8),
        Text(active ? 'Идёт запись' : 'Не записываю', style: const TextStyle(fontSize: 13, color: VVTheme.inkMuted)),
      ],
    );
  }
}
