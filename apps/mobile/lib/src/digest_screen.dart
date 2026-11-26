import 'package:flutter/material.dart';
import 'api_client.dart';

import 'digest_model.dart';
import 'theme.dart';

/// Экран разбора. Три вопроса, на которые человек хочет ответ в первую очередь:
/// что решили, что осталось неясным, что теперь делать. Цитата — под каждой задачей,
/// потому что задача без источника не принимается.
class DigestScreen extends StatefulWidget {
  const DigestScreen({super.key, required this.digest, this.onApprove, this.api, this.sessionId});

  final Digest digest;
  final void Function(Item item)? onApprove;

  /// Сервер и сессия нужны для отправки задач наружу. Могут быть null — тогда экран
  /// остаётся читаемым, но кнопки отправки нет: обещать действие, которого не будет, нельзя.
  final ApiClient? api;
  final String? sessionId;

  @override
  State<DigestScreen> createState() => _DigestScreenState();
}

class _DigestScreenState extends State<DigestScreen> {
  bool _sending = false;
  String _sentMessage = '';
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
          const SizedBox(height: 8),
          _exportBlock(),
        ],
      ),
    );
  }

  /// Отправка одобренных задач наружу.
  ///
  /// Кнопка появляется, только если есть куда отправлять и через что. Иначе человек нажал бы
  /// и получил отказ — а обещание, которое не сбывается, хуже отсутствия кнопки.
  Widget _exportBlock() {
    final api = widget.api;
    final sessionId = widget.sessionId;
    final approved = widget.digest.items.where((i) => i.approved).length;
    if (api == null || sessionId == null || widget.digest.items.isEmpty) {
      return const SizedBox.shrink();
    }
    if (approved == 0) {
      return const Padding(
        padding: EdgeInsets.only(top: 8),
        child: Text('Отметьте нужные задачи — тогда их можно будет отправить.',
            style: TextStyle(color: VVTheme.inkMuted)),
      );
    }
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          FilledButton.icon(
            onPressed: _sending ? null : () => _sendApproved(api, sessionId),
            icon: const Icon(Icons.send),
            label: Text(_sending ? 'Отправляю…' : 'Отправить в задачник'),
          ),
          if (_sentMessage.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(_sentMessage, style: const TextStyle(color: VVTheme.inkMuted)),
            ),
        ],
      ),
    );
  }

  /// Отправляет и говорит человеку правду: сколько ушло, сколько не дошло и почему.
  Future<void> _sendApproved(ApiClient api, String sessionId) async {
    setState(() {
      _sending = true;
      _sentMessage = '';
    });
    // Цель — задачник Helper. Адрес берём с того же сервера, что и разбор: отдельная настройка
    // адреса задачника на телефоне не нужна, пока цель одна.
    final targets = <String, String>{'helper': api.baseUrl};
    final (sent, failed, problem) = await api.exportItems(sessionId, widget.digest.items, targets);
    if (!mounted) return;
    setState(() {
      _sending = false;
      // problem уже содержит правду о частичном провале (его формирует клиент), поэтому
      // второй источник того же текста здесь не нужен — только выбор, что показать.
      _sentMessage = problem.isNotEmpty
          ? problem
          : (sent > 0 ? 'Отправлено задач: ' + sent.toString() + '.' : 'Отправлять было нечего.');
    });
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
