import 'package:flutter/material.dart';

import 'api_client.dart';
import 'providers_model.dart';
import 'server_settings.dart';
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
  const SettingsScreen({super.key, this.api, this.initialServerUrl = ''});

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

  @override
  void dispose() {
    for (final c in keys.values) {
      c.dispose();
    }
    server.dispose();
    super.dispose();
  }

  /// Сохранение адреса: сначала проверяем на опечатки, потом принимаем.
  void _saveServer() {
    final problem = ServerSettings.problem(server.text);
    setState(() => serverProblem = problem);
    if (problem == null) {
      // Адрес нормализован, чтобы склейка с /api/v1/... не давала двойных слэшей
      server.text = ServerSettings.normalize(server.text);
    }
  }

  TextEditingController _keyFor(String id) => keys.putIfAbsent(id, () => TextEditingController());

  Future<void> _probe(ProviderInfo info) async {
    final key = _keyFor(info.id).text;
    final local = KeyCheck.problem(info.id, key);
    if (local != null) {
      setState(() => results[info.id] = Pair('rejected', local));
      return;
    }
    if (widget.api == null) {
      setState(() => results[info.id] = const Pair('unknown', 'Сначала укажите адрес сервера выше.'));
      return;
    }
    setState(() => busy = true);
    try {
      final (verdict, message) = await widget.api!.probe(info.id, key);
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
              OutlinedButton(onPressed: _saveServer, child: const Text('Сохранить')),
            ],
          ),
          if (serverProblem == null && server.text.isNotEmpty)
            const Padding(
              padding: EdgeInsets.only(top: 6),
              child: Text('Адрес принят.', style: TextStyle(color: VVTheme.ok, fontSize: 12)),
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
