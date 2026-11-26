import 'package:flutter/material.dart';

import 'api_client.dart';
import 'digest_model.dart';
import 'digest_screen.dart';
import 'theme.dart';

/// Экран-загрузчик разбора.
///
/// Зачем отдельный слой: [DigestScreen] показывает готовый разбор и ничего не знает о сети.
/// Здесь — только три состояния, и все три видимы человеку, без «пусто и непонятно»:
///   1. грузим — честно написано, что ждём сервер;
///   2. разбора нет — причина словами сервера, а не пустота;
///   3. готово — обычный экран разбора.
class DigestLoader extends StatefulWidget {
  const DigestLoader({
    super.key,
    required this.api,
    this.sessionId,
    this.onApprove,
  });

  final ApiClient api;

  /// Запись, разбор которой нужен. null — разбора ещё нет (запись не ушла на сервер).
  final String? sessionId;

  final void Function(Item item)? onApprove;

  @override
  State<DigestLoader> createState() => _DigestLoaderState();
}

class _DigestLoaderState extends State<DigestLoader> {
  Digest? _digest;
  String _problem = '';
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final id = widget.sessionId;
    if (id == null || id.isEmpty) {
      setState(() {
        _loading = false;
        _problem = 'Разбора ещё нет: запись не отправлена на сервер.';
      });
      return;
    }
    final digest = await widget.api.fetchDigest(id);
    if (!mounted) return;
    setState(() {
      _loading = false;
      _digest = digest;
      _problem = digest == null ? widget.api.lastDigestProblem : '';
    });
  }

  /// Повтор — настоящая повторная загрузка, а не просто спиннер на экране.
  void _retry() {
    setState(() {
      _loading = true;
      _problem = '';
      _digest = null;
    });
    _load();
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      // Голый спиннер не отличает «сервер думает» от «всё зависло». Пишем, что происходит,
      // и что можно сделать, если это надолго: уйти, ничего не потеряв.
      return const Scaffold(
        backgroundColor: VVTheme.bg,
        body: Center(
          child: Padding(
            padding: EdgeInsets.symmetric(horizontal: 32),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                CircularProgressIndicator(),
                SizedBox(height: 16),
                Text('Разбираю разговор: расшифровка, задачи, выжимка.',
                    textAlign: TextAlign.center, style: TextStyle(fontSize: 16)),
                SizedBox(height: 8),
                Text('Обычно это занимает до минуты. Если дольше — можно выйти: запись и звук сохранены '
                    'на сервере, ничего не пропадёт.',
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 13, color: VVTheme.inkMuted, height: 1.4)),
              ],
            ),
          ),
        ),
      );
    }
    final digest = _digest;
    if (digest != null) {
      // Разбор показан — при закрытии сообщаем об этом вызывающему: только тогда запись на телефоне
      // можно стирать. Без этого признака удаление шло бы и после ошибки сервера.
      return PopScope(
        canPop: false,
        // Экран закрывают «назад» или кнопкой: любой уход означает «разбор был показан».
        onPopInvokedWithResult: (didPop, _) {
          if (!didPop) Navigator.of(context).pop(true);
        },
        child: DigestScreen(
          digest: digest,
          onApprove: widget.onApprove,
          api: widget.api,
          sessionId: widget.sessionId,
        ),
      );
    }
    final text = _problem.isEmpty ? 'Разбор не получен.' : _problem;
    return Scaffold(
      backgroundColor: VVTheme.bg,
      appBar: AppBar(backgroundColor: VVTheme.surface, title: const Text('Разбор разговора')),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(text, textAlign: TextAlign.center, style: const TextStyle(color: VVTheme.ink, fontSize: 16)),
              const SizedBox(height: 16),
              OutlinedButton(onPressed: _retry, child: const Text('Повторить')),
            ],
          ),
        ),
      ),
    );
  }
}
