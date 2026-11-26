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
  /// Сколько задач уже ушло. Повторная отправка удвоила бы их в задачнике.
  int _sentCount = 0;
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
                border: Border.all(color: VVTheme.warn),
              ),
              child: const Text(
                'Разобрано только начало: разговор длиннее одного прохода.',
                style: TextStyle(fontSize: 13, height: 1.45),
              ),
            ),
          if (d.topic.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(bottom: 16),
              // Тема — первой и крупнее: это ответ на вопрос «о чём вообще был разговор»,
              // который человек задаёт раньше, чем читает список задач.
              child: Text(
                d.topic,
                style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w600, height: 1.35),
              ),
            ),
          // Заголовок раздела остаётся на месте всегда: пропавший заголовок читается как «здесь ничего нет».
          if (d.summary.isEmpty)
            Padding(
              padding: const EdgeInsets.only(bottom: 20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Коротко', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600)),
                  const SizedBox(height: 8),
                  Text(
                    // Причина пустоты важнее самой пустоты, и она у нас есть: разбор мог обрезаться.
                    d.truncated
                        ? 'В разобранной части модель не выделила главное. Остальное ещё не разобрано.'
                        : 'Модель не выделила главное. Расшифровка записана — откройте её кнопкой «Показать расшифровку».',
                    style: const TextStyle(fontSize: 14, height: 1.45, color: VVTheme.inkMuted),
                  ),
                ],
              ),
            )
          else
            _section('Коротко', d.summary),
          if (_noiseLine(d) != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              // Отсечённый шум объясняет, почему в расшифровке есть провалы. Без этой строки
              // человек считает, что в тишине ничего не говорили, а не что звук выбросили.
              child: Text(_noiseLine(d)!, style: const TextStyle(fontSize: 12, color: VVTheme.inkMuted)),
            ),
          if (d.budgetRub != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              // Перерасход — не мелочь в подвале: он должен бросаться в глаза до чтения выжимки.
              child: Text(
                'Встреча вышла дороже предела ' + d.budgetRub!.toStringAsFixed(2) + ' ₽ — запись продолжается, но стоит проверить, нужна ли такая длина.',
                style: const TextStyle(fontSize: 13, height: 1.4, color: VVTheme.ink),
              ),
            ),
          if (_costLine(d) != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              // Стоимость видна до того, как человек начнёт листать: счёт за встречу важнее красоты.
              child: Text(_costLine(d)!, style: const TextStyle(fontSize: 12, color: VVTheme.inkMuted)),
            ),
          if (d.summaryHidden > 0)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              // Показана часть — говорим прямо. Иначе человек считает, что главное он увидел.
              child: Text('Ещё ' + d.summaryHidden.toString() + ' пунктов выжимки не показаны — они в ответе сервера.',
                  style: const TextStyle(fontSize: 12, color: VVTheme.inkMuted)),
            ),
          if (d.errors.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(bottom: 16),
              // Разбор сохранён частично — говорим до того, как человек начнёт ему верить.
              child: Text(
                'Разбор прошёл не полностью: ' + d.errors.join('; ') + '. Проверьте расшифровку перед отправкой задач.',
                style: const TextStyle(fontSize: 13, height: 1.4, color: VVTheme.ink),
              ),
            ),
          if (d.rejected.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(bottom: 16),
              // Честность важнее полноты: лучше сказать «это не подтверждено словами»,
              // чем выдать догадку модели за задачу.
              child: Text(
                'Не подтверждено словами, поэтому не добавлено: ' + d.rejected.join('; '),
                style: const TextStyle(fontSize: 13, color: VVTheme.inkMuted, height: 1.4),
              ),
            ),
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
            // Повторное нажатие после успеха создало бы дубли задач в чужой системе — отменить это
            // из приложения нельзя. Отправляем ещё раз только если что-то НЕ дошло.
            onPressed: (_sending || _sentCount > 0) ? null : () => _sendApproved(api, sessionId),
            icon: Icon(_sentCount > 0 ? Icons.check : Icons.send),
            label: Text(_sending
                ? 'Отправляю…'
                : (_sentCount > 0 ? 'Уже отправлено: ' + _sentCount.toString() : 'Отправить в задачник')),
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
    final result = await api.exportItems(sessionId, widget.digest.items, targets);
    if (!mounted) return;
    setState(() {
      _sending = false;
      // problem уже содержит правду о частичном провале (его формирует клиент), поэтому
      // второй источник того же текста здесь не нужен — только выбор, что показать.
      // Счётчик сбрасывается при частичном провале: дослать недоехавшее — можно, дубли — нельзя.
      // Досылать можно, только если ничего не потерялось: иначе повтор удвоил бы уже доехавшее.
      _sentCount = (result.failed > 0 || result.skipped > 0) ? 0 : result.sent;
      _sentMessage = result.problem.isNotEmpty
          ? result.problem
          : (result.sent > 0
              ? 'Отправлено задач: ' + result.sent.toString() + '.'
              : 'Отправлять было нечего.');
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
              child: Text([item.owner, item.dueHuman].where((s) => s.isNotEmpty).join(' · '),
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

/// Строка про израсходованное аудио и деньги.
///
/// null — говорить нечего: сервер не прислал ни секунд, ни цены. «0 ₽» не показываем никогда,
/// потому что ноль здесь означает «тариф не задан», а не «встреча была бесплатной».
String? _costLine(Digest d) {
  final cost = d.costRub;
  final seconds = d.sentSeconds;
  if (cost == null && (seconds == null || seconds <= 0)) return null;
  final minutes = ((seconds ?? 0) / 60).toStringAsFixed(seconds != null && seconds < 60 ? 1 : 0);
  final parts = <String>[];
  if (seconds != null && seconds > 0) parts.add('В распознавание ушло ~' + minutes + ' мин');
  if (cost != null) parts.add('≈ ' + cost.toStringAsFixed(2) + ' ₽');
  return parts.join(' · ') + '.';
}

/// Строка про отсечённый шум. null — отсекать было нечего или сервер не сказал.
///
/// Кадр у нас 20 мс, поэтому число кадров переводим в секунды: «24000 кадров» человеку ничего не говорит.
String? _noiseLine(Digest d) {
  final seconds = (d.droppedNoise * 20 / 1000).round();
  // Тишина, не ушедшая в распознавание: именно эти секунды не оплачены провайдеру.
  final silence = (d.droppedByVad * 20 / 1000).round();
  final parts = <String>[];
  if (silence >= 1) parts.add('Тишины не отправлено: ~' + silence.toString() + ' с');
  if (seconds >= 1) parts.add('отсечено как шум: ~' + seconds.toString() + ' с');
  if (d.droppedInvented > 0) parts.add('в тишине отброшено ' + d.droppedInvented.toString() + ' выдуманных строк');
  if (parts.isEmpty) return null;
  return parts.join(' · ') + '.';
}
