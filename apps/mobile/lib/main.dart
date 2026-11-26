import 'dart:async';

import 'package:flutter/material.dart';

import 'src/api_client.dart';
import 'src/audio_file.dart';
import 'src/consent_model.dart';
import 'src/digest_loader.dart';
import 'src/consent_store.dart';
import 'src/prefs_key_value_store.dart' as prefs;
import 'src/method_channel_bridge.dart';
import 'src/prefs_server_store.dart';
import 'src/recording_controller.dart';
import 'src/server_scope.dart';
import 'src/session_model.dart';
import 'src/settings_screen.dart';
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
      home: ServerScopeLoader(
        store: PrefsServerStore(),
        tokenStore: PrefsTokenStore(),
        // Адрес и токен читаются до первого экрана: иначе настройки не действовали бы вовсе.
        child: (_) => ListenScreen(controller: RecordingController(MethodChannelBridge())),
      ),
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
  final SessionModel session = SessionModel();
  Timer? _ticker;
  final ConsentStore consentStore = ConsentStore(store: prefs.PrefsKeyValueStore());

  /// Идёт отправка записи на сервер: кнопка разбора в это время не врёт «готово».
  bool _uploading = false;

  /// Идентификатор сессии на сервере для последней успешной отправки.
  String? _sessionId;

  /// Уже отправленных кусков: контроллер хранит только последний, поэтому сравниваем счётчик.
  int _sentChunks = 0;

  /// Сколько кусков оказались тишиной и не ушли в сеть.
  int _quietChunks = 0;

  /// Отправка идёт: не плодим параллельные запросы, иначе куски придут вразнобой.
  bool _sendingChunk = false;

  /// Идентификатор сессии для живого текста (открывается заранее, без записи).
  String? _liveSessionId;

  /// Забирает новый кусок звука у контроллера и отправляет на сервер.
  ///
  /// Почему по счётчику, а не по событию: контроллер уведомляет о любом изменении (уровень,
  /// состояние), и без защиты каждый тик отправлял бы один и тот же кусок заново.
  Future<void> _pumpLiveAudio() async {
    if (_sendingChunk) return;
    final received = widget.controller.audioChunksReceived;
    if (received <= _sentChunks) return;
    final chunk = widget.controller.lastAudioChunk;
    if (chunk == null || chunk.isEmpty) return;
    final scope = ServerScope.maybeOf(context);
    if (scope == null) return;
    final api = scope.config.api;
    // Тишину не гоняем через мобильный интернет: час молчания — это десятки мегабайт трафика
    // человека и ни одного слова в расшифровке.
    if (!api.isAudible(chunk)) {
      _sentChunks = received;
      _quietChunks += 1;
      return;
    }
    _sendingChunk = true;
    _sentChunks = received;
    try {
      _liveSessionId ??= await api.openSession();
      final id = _liveSessionId;
      if (id == null) return;
      var text = await api.sendLiveChunk(id, chunk);
      if (text == null) {
        // Одна повторная попытка: чаще всего это моргнувшая сеть, а не отказ сервера.
        // Терять сказанное молча нельзя — «умный диктофон», который пропускает слова, хуже диктофона.
        text = await api.sendLiveChunk(id, chunk);
        if (text == null) api.chunksLost += 1;
      }
      if (!mounted) return;
      final got = text;
      if (got != null && got.isNotEmpty) {
        setState(() => widget.controller.liveText = got);
      } else if (api.chunksLost > 0) {
        setState(() => widget.controller.liveWarning =
            'Часть звука не дошла до сервера (' + api.chunksLost.toString() + '). Текст может быть неполным.');
      }
    } finally {
      _sendingChunk = false;
    }
  }

  /// Открывает разбор: сначала убеждается, что запись отправлена, иначе разбирать нечего.
  Future<void> _openDigest(ApiClient api) async {
    final path = widget.controller.lastSavedPath;
    if (_sessionId == null && path.isEmpty) {
      // Записи нет — экран разбора сам объяснит, чего не хватает, без выдумок.
      if (!mounted) return;
      await Navigator.of(context).push(
        MaterialPageRoute<void>(builder: (_) => DigestLoader(api: api)),
      );
      return;
    }
    // Живой режим: сессия открыта, но звук на сервере не сохранён (живой текст шёл кусками).
    // Файл записи — единственный путь к точному разбору, поэтому грузим его под тем же id.
    if (_sessionId != null && path.isNotEmpty) {
      setState(() => _uploading = true);
      try {
        final bytes = await readFileBytes(path);
        final id = await api.uploadSession(bytes, sessionId: _sessionId);
        if (!mounted) return;
        setState(() => _uploading = false);
        if (id == null) {
          widget.controller.lastError = api.lastUploadProblem;
        } else {
          // Разбор не начинается сам — ни после загрузки, ни по живому тексту.
          // Без этого живая встреча грузилась и навсегда оставалась «ещё не готов».
          final started = await api.startAnalysis(id);
          if (!started && mounted) widget.controller.lastError = api.lastAnalysisProblem;
        }
      } catch (e) {
        if (mounted) setState(() => _uploading = false);
        widget.controller.lastError = 'Не удалось прочитать запись: ' + e.toString();
      }
    }
    if (_sessionId == null) {
      setState(() => _uploading = true);
      try {
        final bytes = await readFileBytes(path);
        final id = await api.uploadSession(bytes);
        if (!mounted) return;
        if (id == null) {
          setState(() {
            _uploading = false;
            widget.controller.lastError = api.lastUploadProblem;
          });
          return;
        }
        _sessionId = id;
        // Запись на сервере есть, но разбор сам не начнётся: просим явно.
        // Ошибку запуска не глотаем — иначе экран покажет «ещё не готов» вместо настоящей причины.
        final started = await api.startAnalysis(id);
        if (!started && mounted) {
          setState(() {
            _uploading = false;
            widget.controller.lastError = api.lastAnalysisProblem;
          });
          return;
        }
      } catch (e) {
        if (mounted) {
          setState(() {
            _uploading = false;
            widget.controller.lastError = 'Не удалось прочитать запись: ' + e.toString();
          });
        }
        return;
      }
      if (mounted) setState(() => _uploading = false);
    }
    if (!mounted) return;
    final sessionId = _sessionId;
    await Navigator.of(context).push(
      MaterialPageRoute<void>(builder: (_) => DigestLoader(api: api, sessionId: sessionId)),
    );
    // Разбор открыт и закрыт — сервер запись получил. Только теперь её можно убрать с телефона.
    // Раньше — нет: иначе человек с кончившимся местом потеряет разговор ради двух мегабайт.
    if (sessionId != null && path.isNotEmpty) {
      await deleteRecording(path);
    }
  }

  /// Согласие на запись: приложение слушает чужие голоса, и человек должен знать это заранее.
  ConsentModel consent = ConsentModel(
    version: '2026-11-01',
    terms: const [
      'Приложение слушает разговор через микрофон и сохраняет расшифровку.',
      'Текст и записи хранятся на указанном вами сервере, а не пересылаются третьим лицам без вашего ведома.',
      'Запись разговора может требовать согласия его участников — это ваша ответственность, приложение не заменяет её.',
    ],
  );

  /// Старт с проверкой согласия: без него запись не начинается вовсе.
  Future<void> _startWithConsent() async {
    if (!consent.canRecord) {
      final accepted = await showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('Перед записью'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: consent.terms
                .map((line) => Padding(
                      padding: const EdgeInsets.only(bottom: 8),
                      child: Text('• ' + line),
                    ))
                .toList(),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.of(ctx).pop(false), child: const Text('Отмена')),
            FilledButton(onPressed: () => Navigator.of(ctx).pop(true), child: const Text('Понимаю, начать')),
          ],
        ),
      );
      if (accepted != true) return;
      if (!mounted) return;
      setState(() => consent = consent.accept());
      await consentStore.save(consent);
    }
    // Телефон может убить запись в фоне — предупреждаем ДО, а не объясняем после потери встречи.
    if (!await _warnIfBatteryRestricted()) return;
    if (!mounted) return;
    await widget.controller.start();
  }

  /// Возвращает false, если человек отказался начинать.
  Future<bool> _warnIfBatteryRestricted() async {
    final bridge = widget.controller.bridge;
    final restricted = await bridge.batteryRestricted();
    if (!restricted || !mounted) return true;
    final startFromDialog = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Телефон может оборвать запись'),
        content: const Text(
            'Система ограничивает работу приложений в фоне. На Xiaomi, Huawei и части Samsung запись '
            'может остановиться, когда экран погаснет.'),
        actions: [
          TextButton(onPressed: () => Navigator.of(ctx).pop(false), child: const Text('Позже')),
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Всё равно начать'),
          ),
          // Главная кнопка — безопасная: ошибиться пальцем в сторону потери записи нельзя.
          FilledButton(
            onPressed: () async {
              await bridge.openBatterySettings();
              if (!mounted) return;
              // Настройки не гарантируют разрешение: перечитываем факт, а не верим, что человек нажал.
              final stillRestricted = await bridge.batteryRestricted();
              if (!mounted) return;
              if (stillRestricted) {
                final anyway = await showDialog<bool>(
                  context: context,
                  builder: (ctx2) => AlertDialog(
                    title: const Text('Разрешение не выдано'),
                    content: const Text(
                        'Запись начнётся, но система может остановить её, когда экран погаснет. '
                        'Можно разрешить позже в настройках телефона.'),
                    actions: [
                      TextButton(onPressed: () => Navigator.of(ctx2).pop(false), child: const Text('Отмена')),
                      TextButton(onPressed: () => Navigator.of(ctx2).pop(true), child: const Text('Начать всё равно')),
                    ],
                  ),
                );
                if (anyway != true) return;
              }
              if (mounted) await widget.controller.start();
            },
            child: const Text('Разрешить'),
          ),
        ],
      ),
    );
    // true — человек выбрал «Всё равно начать»: запись стартует ниже, в _startWithConsent.
    // false — «Позже», отмена после настроек, или запись уже запущена внутри «Разрешить».
    return startFromDialog == true;
  }

  @override
  void initState() {
    super.initState();
    widget.controller.bind();
    // Согласие поднимается из хранилища: спрашивать одно и то же каждый пуск — значит добиться,
    // чтобы его перестали читать.
    consentStore.load(consent).then((loaded) {
      if (mounted) setState(() => consent = loaded);
    });
    // Тик раз в секунду: время записи — факт, который человек проверяет глазами.
    _ticker = Timer.periodic(const Duration(seconds: 1), (_) {
      if (!mounted) return;
      setState(() => session.tick(recording: widget.controller.state == RecordingState.recording));
    });
    widget.controller.changes.listen((_) {
      if (mounted) setState(() {});
      _pumpLiveAudio();
    });
  }

  @override
  void dispose() {
    _ticker?.cancel();
    widget.controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final scope = ServerScope.maybeOf(context)!;
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
                  const SizedBox(width: 8),
                  IconButton(
                    tooltip: 'Подключение моделей',
                    icon: const Icon(Icons.tune, size: 20, color: VVTheme.inkMuted),
                    onPressed: () => Navigator.of(context).push(
                      MaterialPageRoute<void>(
                        builder: (_) => SettingsScreen(
                          api: scope.config.api,
                          initialServerUrl: scope.serverUrl,
                          store: PrefsServerStore(),
                        ),
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Row(
                children: [
                  Text(session.clock, style: const TextStyle(fontSize: 34, fontWeight: FontWeight.w300, fontFeatures: [FontFeature.tabularFigures()])),
                  const Spacer(),
                  if (recording)
                    OutlinedButton.icon(
                      onPressed: () => setState(() => session.mark()),
                      icon: const Icon(Icons.bookmark_add_outlined, size: 18),
                      label: const Text('Метка'),
                    ),
                ],
              ),
              if (session.marks.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(top: 6),
                  child: Text(
                    'Метки: ' + session.marks.map((m) => m.clock).join(', '),
                    style: const TextStyle(color: VVTheme.inkMuted, fontSize: 12),
                  ),
                ),
              if (session.hint != null)
                Padding(
                  padding: const EdgeInsets.only(top: 6),
                  child: Text(session.hint!, style: const TextStyle(color: VVTheme.warn, fontSize: 12)),
                ),
              const SizedBox(height: 16),
              Expanded(
                child: SingleChildScrollView(
                  child: Text(
                    c.liveText.isEmpty ? 'Пока тихо. Нажмите «Слушаю» — я начну расшифровывать.' : c.liveText,
                    style: TextStyle(fontSize: 16, height: 1.5, color: c.liveText.isEmpty ? VVTheme.inkMuted : VVTheme.ink),
                  ),
                ),
              ),
              if (recording && _quietChunks >= 4)
                const Padding(
                  padding: EdgeInsets.only(top: 8),
                  child: Text(
                    'Пока слишком тихо — проверьте, что микрофон не закрыт.',
                    style: TextStyle(color: VVTheme.warn, fontSize: 12),
                  ),
                ),
              if (recording && (ServerScope.maybeOf(context)?.config.api.lastLiveProblem.isNotEmpty ?? false))
                Padding(
                  padding: const EdgeInsets.only(top: 12),
                  child: Text(
                    // Молчать нельзя: «пока тихо» и «сервер не принимает звук» — разные причины,
                    // и человек должен знать, какая из них.
                    'Живая расшифровка не идёт: ' +
                        (ServerScope.maybeOf(context)?.config.api.lastLiveProblem ?? ''),
                    style: const TextStyle(fontSize: 13, color: VVTheme.warnSoft),
                  ),
                ),
              if (c.liveWarning.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(top: 12),
                  child: Text(c.liveWarning,
                      style: const TextStyle(fontSize: 13, color: VVTheme.warnSoft)),
                ),
              if (c.lastError.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(bottom: 16),
                  child: Text(c.lastError, style: const TextStyle(color: VVTheme.warn, fontSize: 14)),
                ),
              // Разбор становится доступен после первой записи: до этого разбирать нечего.
              if (session.seconds > 0 && !recording)
                Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: OutlinedButton(
                    onPressed: () => _openDigest(scope.config.api),
                    child: Text(_uploading ? 'Отправляю запись…' : 'Открыть разбор'),
                  ),
                ),
                            // Одна главная кнопка: действие зависит от состояния, без второй «кнопки отмены».
              SizedBox(
                height: 64,
                child: FilledButton(
                  style: FilledButton.styleFrom(backgroundColor: recording ? VVTheme.live : VVTheme.accent),
                  onPressed: recording
                      ? () async {
                          await c.stop();
                          if (mounted) setState(() {});
                        }
                      : _startWithConsent,
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
