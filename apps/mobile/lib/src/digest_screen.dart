import 'package:flutter/material.dart';

import 'digest_model.dart';
import 'theme.dart';

/// Экран разбора. Три вопроса, на которые человек хочет ответ в первую очередь:
/// что решили, что осталось неясным, что теперь делать. Цитата — под каждой задачей,
/// потому что задача без источника не принимается.
class DigestScreen extends StatefulWidget {
  const DigestScreen({super.key, required this.digest, this.onApprove});

  final Digest digest;
  final void Function(Item item)? onApprove;

  @override
  State<DigestScreen> createState() => _DigestScreenState();
}

class _DigestScreenState extends State<DigestScreen> {
  @override
  Widget build(BuildContext context) {
    final d = widget.digest;
    return Scaffold(
      backgroundColor: VVTheme.bg,
      appBar: AppBar(
        backgroundColor: VVTheme.surface,
        title: const Text('Разбор разговора'),
      ),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          _section('Коротко', d.summary),
          _section('Решили', d.decisions),
          _section('Осталось неясным', d.openQuestions),
          const SizedBox(height: 8),
          const Text('Задачи', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600)),
          const SizedBox(height: 12),
          if (d.items.isEmpty)
            const Text('Разбор не нашёл задач с цитатой.', style: TextStyle(color: VVTheme.inkMuted))
          else
            ...d.items.map((item) => _ItemCard(item: item, onApprove: () {
                  setState(() => item.approved = true);
                  widget.onApprove?.call(item);
                })),
        ],
      ),
    );
  }

  Widget _section(String title, List<String> lines) {
    if (lines.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(bottom: 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600)),
          const SizedBox(height: 8),
          ...lines.map((line) => Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Text('• ' + line, style: const TextStyle(fontSize: 15, height: 1.45)),
              )),
        ],
      ),
    );
  }
}

class _ItemCard extends StatelessWidget {
  const _ItemCard({required this.item, required this.onApprove});

  final Item item;
  final VoidCallback onApprove;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(color: VVTheme.surface, borderRadius: BorderRadius.circular(14)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(item.kindLabel, style: const TextStyle(color: VVTheme.accent, fontSize: 12, fontWeight: FontWeight.w600)),
              const Spacer(),
              Text(item.timecode, style: const TextStyle(color: VVTheme.inkMuted, fontSize: 12)),
            ],
          ),
          const SizedBox(height: 6),
          Text(item.title, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
          if (item.owner.isNotEmpty || item.due.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text([item.owner, item.due].where((s) => s.isNotEmpty).join(' · '),
                  style: const TextStyle(color: VVTheme.inkMuted, fontSize: 13)),
            ),
          const SizedBox(height: 10),
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(color: VVTheme.bg, borderRadius: BorderRadius.circular(8)),
            child: Text('«' + item.quote + '»', style: const TextStyle(fontStyle: FontStyle.italic, fontSize: 14, height: 1.4)),
          ),
          const SizedBox(height: 10),
          Align(
            alignment: Alignment.centerRight,
            child: item.approved
                ? const Text('Принято', style: TextStyle(color: VVTheme.ok, fontSize: 13))
                : OutlinedButton(onPressed: onApprove, child: const Text('Принять')),
          ),
        ],
      ),
    );
  }
}
