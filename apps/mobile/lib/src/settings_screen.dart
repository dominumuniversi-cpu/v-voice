import 'package:flutter/material.dart';

import 'api_client.dart';
import 'providers_model.dart';
import 'server_settings.dart';
import 'server_store.dart';
import 'server_scope.dart';
import 'theme.dart';

/// Экран «Подключение моделей» (FR-24..FR-26).
///
/// Решения интерфейса:
///  - пресеты сверху: человеку проще выбрать намерение («точно / дёшево / приватно»),
///    чем разбираться, чем Speechmatics отличается от Deepgram;
///  - у каждого провайдера короткая честная подпись: где данные, что с качеством, нужен ли ключ;
///  - «Проверить» сначала прогоняет простые правила на телефоне (пустой ключ, пробел, обрезок)
///    и только потом идёт в сеть — так человек получает ответ мгновенно, без ожидания.
class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key, this.api, this.initialServerUrl = '', this.store});

  /// Хранилище адреса. Если null — адрес живёт только до закрытия экрана.
  final ServerStore? store;

  /// Клиент сервера. Если null — проверка ключа недоступна (экран работает автономно).
  final ApiClient? api;
  final String initialServerUrl;

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class Pair {
  const Pair(this.verdict, this.message);
  final String verdict;
  final String message;
}

class _SettingsScreenState extends State<SettingsScreen> {
  String selectedKind = 'asr';
  String? activePreset;
  final Map<String, TextEditingController> keys = {};
  final Map<String, Pair> results = {};
  late TextEditingController server = TextEditingController(text: widget.initialServerUrl);
  bool busy = false;
  String? serverProblem;
  String? savedNote;

  /// Keeper: одно правило на чтение и запись адреса — то же, что проверено тестами.
  ServerSettingsKeeper? get _keeper => widget.store == null
      ? null
      : ServerSettingsKeeper(
          store: widget.store!,
          validate: ServerSettings.problem,
          normalize: ServerSettings.normalize,
        );

  @override
  void initState() {
    super.initState();
    final keeper = _keeper;
    if (keeper != null) {
      keeper.load(widget.initialServerUrl).then((url) {
        if (!mounted) return;
        setState(() => server.text = url);
      });
    }
    // Загрузка моделей сюда НЕ ставится: _client читает ServerScope (InheritedWidget),
    // а обращаться к нему из initState нельзя — Flutter просто выбрасывает исключение.
    // Место для этого — didChangeDependencies, который вызывается сразу после initState.
  }

  /// Первый вход и любая смена адреса сервера: здесь уже можно читать ServerScope.
  bool _modelsRequested = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_modelsRequested) return;
    _modelsRequested = true;
    _loadServerModels();
  }

  @override
  void dispose() {
    for (final c in keys.values) {
      c.dispose();
    }
    server.dispose();
    super.dispose();
  }

  /// Сохранение адреса: сначала проверяем на опечатки, потом принимаем.
  Future<void> _saveServer() async {
    final keeper = _keeper;
    final problem = keeper == null
        ? ServerSettings.problem(server.text)
        : await keeper.save(server.text);
    if (!mounted) return;
    setState(() {
      serverProblem = problem;
      savedNote = problem == null ? 'Адрес сохранён.' : null;
      if (problem == null) {
        // Нормализуем и показываем то, что реально уйдёт в запросы
        server.text = ServerSettings.normalize(server.text);
      }
    });
    // Сохранение действует сразу: без этого адрес менялся бы только после перезапуска.
    if (problem == null) {
      await ServerScope.maybeOf(context)?.onChanged(server.text.trim());
    }
  }

  TextEditingController _keyFor(String id) => keys.putIfAbsent(id, () => TextEditingController());

  /// Клиент действующего адреса: если человек поменял адрес, проверка уйдёт на новый,
  /// а не на тот, что был при открытии экрана.
  ApiClient? get _client => ServerScope.maybeOf(context)?.config.api ?? widget.api;

  /// Состояние моделей на сервере: загружается при открытии экрана.
  /// Показывается словами, а не флагами: человеку нужно понять «работает или нет», а не разбирать JSON.
  Map<String, dynamic>? _serverModels;
  bool _modelsLoading = true;

  Future<void> _loadServerModels() async {
    // Любая ошибка сети — это «состояние неизвестно», а не падение экрана: настройки должны
    // открываться и без сервера, иначе человек останется без возможности исправить адрес.
    Map<String, dynamic>? health;
    try {
      health = await _client?.fetchHealth();
    } catch (_) {
      health = null;
    }
    if (!mounted) return;
    setState(() {
      _serverModels = health;
      _modelsLoading = false;
    });
  }

  /// Что на сервере настроено: без этого человек не знает, подключены ли модели вообще,
  /// и будет искать поле для ключа, которого на телефоне больше нет.
  Widget _serverStatusCard() {
    if (_modelsLoading) {
      return const Text('Проверяю, что подключено на сервере…',
          style: TextStyle(color: VVTheme.inkMuted));
    }
    final models = _serverModels;
    if (models == null) {
      return const Text('Сервер не ответил — подключение моделей неизвестно.',
          style: TextStyle(color: VVTheme.inkMuted));
    }
    final asr = models['asr'] is Map ? Map<String, dynamic>.from(models['asr'] as Map) : null;
    final llm = models['llm'] is Map ? Map<String, dynamic>.from(models['llm'] as Map) : null;
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: VVTheme.surface,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(_modelLine('Распознавание речи', asr)),
          const SizedBox(height: 4),
          Text(_modelLine('Понимание разговора', llm)),
          const SizedBox(height: 8),
          const Text('Ключи задаются на сервере и на телефон не попадают.',
              style: TextStyle(fontSize: 12, color: VVTheme.inkMuted)),
        ],
      ),
    );
  }

  /// Подпись про одну модель: что подключено и готово ли. Без ключей и их фрагментов.
  String _modelLine(String title, Map<String, dynamic>? part) {
    if (part == null) return title + ': сервер не ответил';
    final provider = (part['provider'] ?? '').toString();
    final ready = part['ready'] == true;
    if (provider.isEmpty) return title + ': не подключена';
    return title + ': ' + provider + (ready ? ' — готово' : ' — ключ не указан');
  }

  Future<void> _probe(ProviderInfo info) async {
    final key = _keyFor(info.id).text;
    final local = KeyCheck.problem(info.id, key);
    if (local != null) {
      setState(() => results[info.id] = Pair('rejected', local));
      return;
    }
    final client = _client;
    if (client == null) {
      setState(() => results[info.id] = const Pair('unknown', 'Сначала укажите адрес сервера выше.'));
      return;
    }
    setState(() => busy = true);
    try {
      final (verdict, message) = await client.probe(info.id, key);
      setState(() => results[info.id] = Pair(verdict, message));
    } catch (e) {
      setState(() => results[info.id] = Pair('rejected', 'Не удалось соединиться: ' + e.toString()));
    } finally {
      setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final list = kProviders.where((p) => p.kind == selectedKind).toList();
    return Scaffold(
      backgroundColor: VVTheme.bg,
      appBar: AppBar(backgroundColor: VVTheme.surface, title: const Text('Подключение моделей')),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          const Text('Сервер', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
          const SizedBox(height: 8),
          _serverStatusCard(),
          const SizedBox(height: 20),
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: server,
                  keyboardType: TextInputType.url,
                  decoration: InputDecoration(
                    hintText: 'https://…',
                    isDense: true,
                    errorText: serverProblem,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              OutlinedButton(onPressed: () { _saveServer(); }, child: const Text('Сохранить')),
            ],
          ),
          if (savedNote != null)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text(savedNote!, style: const TextStyle(color: VVTheme.ok, fontSize: 12)),
            ),
          const SizedBox(height: 24),
          const Text('Готовые наборы настроек', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            children: kPresets.entries.map((e) {
              final active = activePreset == e.key;
              return ChoiceChip(
                label: Text(e.value['title']!),
                selected: active,
                onSelected: (_) => setState(() => activePreset = e.key),
              );
            }).toList(),
          ),
          if (activePreset != null)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(kPresets[activePreset]!['hint']!, style: const TextStyle(color: VVTheme.inkMuted, fontSize: 13)),
            ),
          const SizedBox(height: 24),
          SegmentedButton<String>(
            segments: const [
              ButtonSegment(value: 'asr', label: Text('Распознавание')),
              ButtonSegment(value: 'llm', label: Text('Разбор')),
            ],
            selected: {selectedKind},
            onSelectionChanged: (s) => setState(() => selectedKind = s.first),
          ),
          const SizedBox(height: 16),
          ...list.map(_providerCard),
        ],
      ),
    );
  }

  Widget _providerCard(ProviderInfo info) {
    final pair = results[info.id];
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(color: VVTheme.surface, borderRadius: BorderRadius.circular(14)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(info.title, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
          const SizedBox(height: 4),
          Text(info.note, style: const TextStyle(color: VVTheme.inkMuted, fontSize: 13, height: 1.4)),
          if (info.needsKey) ...[
            const SizedBox(height: 10),
            TextField(
              controller: _keyFor(info.id),
              obscureText: true,
              decoration: const InputDecoration(hintText: 'Ключ доступа', isDense: true),
            ),
            const SizedBox(height: 4),
            // Человек проверяет ключ и должен понимать, что дальше: иначе он думает,
            // что приложение запомнит ключ, и удивляется, почему запись молчит.
            const Text(
              'На телефоне не хранится: «Проверить» отправляет ключ на сервер и ничего не запоминает.',
              style: TextStyle(color: VVTheme.inkMuted, fontSize: 12, height: 1.3),
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                OutlinedButton(
                  onPressed: busy ? null : () => _probe(info),
                  child: const Text('Проверить'),
                ),
                const SizedBox(width: 12),
                if (pair != null)
                  Expanded(
                    child: Text(
                      pair.message,
                      style: TextStyle(
                        fontSize: 12,
                        color: pair.verdict == 'working' ? VVTheme.ok : VVTheme.warn,
                      ),
                    ),
                  ),
              ],
            ),
          ] else
            const Padding(
              padding: EdgeInsets.only(top: 8),
              child: Text('Ключ не нужен: работает на вашем оборудовании.', style: TextStyle(color: VVTheme.ok, fontSize: 13)),
            ),
        ],
      ),
    );
  }
}
