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
  bool _transcriptBusy = false;
  String _sentMessage = '';
  /// Показывает расшифровку человеку: сначала выбор формата, потом сам текст.
  ///
  /// Форматы именно те, что пригодятся: txt — читать, srt — монтировать видео, md — вставить в заметки.
  Future<void> _showTranscript(ApiClient api, String sessionId) async {
    final format = await showModalBottomSheet<String>(
      context: context,
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Padding(
              padding: EdgeInsets.all(16),
              child: Text('В каком виде сохранить?', style: TextStyle(fontWeight: FontWeight.w600)),
            ),
            ListTile(title: const Text('Текст (.txt)'), subtitle: const Text('Читать целиком'),
                onTap: () => Navigator.pop(ctx, 'txt')),
            ListTile(title: const Text('Субтитры (.srt)'), subtitle: const Text('Для видео и монтажа'),
                onTap: () => Navigator.pop(ctx, 'srt')),
            ListTile(title: const Text('Заметки (.md)'), subtitle: const Text('Вставить в редактор'),
                onTap: () => Navigator.pop(ctx, 'md')),
          ],
        ),
      ),
    );
    if (format == null || !mounted) return;
    setState(() => _transcriptBusy = true);
    final (text, problem) = await api.fetchTranscript(sessionId, format);
    if (!mounted) return;
    setState(() => _transcriptBusy = false);
    if (text == null) {
      // Не пустой экран: человек должен понять, почему файла нет.
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(problem)));
      return;
    }
    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Расшифровка · ' + format),
        content: SizedBox(
          width: double.maxFinite,
          child: SingleChildScrollView(child: SelectableText(text)),
        ),
        actions: [TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Закрыть'))],
      ),
    );
  }

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
          // Разговор длиннее одного прохода модели: говорим об этом сверху, а не мелким шрифтом внизу.
          if (d.truncated)
            Container(
              margin: const EdgeInsets.only(bottom: 16),
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: VVTheme.surface,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: const Color(0xFFE0A030)),
              ),
              child: const Text(
                'Разговор длиннее, чем помещается в один проход. Разобрано начало — остальное пока не разобрано, '
                'это не значит, что там ничего не говорили.',
                style: TextStyle(fontSize: 13, height: 1.45),
              ),
            ),
          if (d.summary.isEmpty)
            // Пустой раздел молча исчезает — и человек не отличит «обсуждать было нечего»
            // от «модель не справилась». Говорим, что именно произошло.
            const Padding(
              padding: EdgeInsets.only(bottom: 20),
              child: Text(
                'Модель не выделила главное. Это не значит, что разговор был пустым — '
                'посмотрите расшифровку и задачи ниже.',
                style: TextStyle(fontSize: 14, height: 1.45, color: VVTheme.inkMuted),
              ),
            )
          else
            _section('Коротко', d.summary),
          _participants(d.participants),
          _section('Решили', d.decisions),
          _section('Осталось неясным', d.openQuestions),
          if (widget.api != null && widget.sessionId != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: OutlinedButton.icon(
                onPressed: _transcriptBusy ? null : () => _showTranscript(widget.api!, widget.sessionId!),
                icon: const Icon(Icons.description_outlined),
                label: Text(_transcriptBusy ? 'Готовлю файл…' : 'Показать расшифровку'),
              ),
            ),
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
    // Цель — задачник Helper. Адрес задаёт СЕРВЕР из своих настроек: телефон не должен ни знать,
    // где живёт задачник, ни уметь отправить задачу сам себе. Пустое значение = «решает сервер».
    final targets = <String, String>{'helper': ''};
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

  /// Кто участвовал и чей это голос. Без этого не видно, откуда взялись задачи и почему
  /// часть речи не попала в разбор — а именно это человек и покупает: «понимать, что происходит».
  Widget _participants(List<List<String>> people) {
    if (people.isEmpty) return const SizedBox.shrink();
    String label(String verdict) {
      if (verdict == 'owner') return ' — свой';
      if (verdict == 'foreign') return ' — чужой голос, в задачи не идёт';
      return ' — участник';
    }
    return Padding(
      padding: const EdgeInsets.only(bottom: 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Кто говорил', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600)),
          const SizedBox(height: 8),
          ...people.map((p) => Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Text('• ' + p[0] + label(p.length > 1 ? p[1] : 'member'),
                    style: const TextStyle(color: VVTheme.inkMuted)),
              )),
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
