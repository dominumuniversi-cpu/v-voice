import 'package:flutter/material.dart';

import 'theme.dart';

/// Записи, которые лежат на телефоне, но о которых приложение не знает.
///
/// Почему это существует: телефон может убить процесс во время записи. Файл остаётся целым
/// (заголовок WAV обновляется по ходу записи), но экран о нём не знает — и разговор пропадает,
/// хотя он рядом. Здесь человек видит такие записи и может отправить их на разбор.
class RecoveredScreen extends StatelessWidget {
  const RecoveredScreen({super.key, required this.recordings, required this.onOpen, required this.onDelete});

  /// Путь, имя, размер в байтах, время изменения (мс).
  final List<Map<String, Object>> recordings;
  final void Function(String path) onOpen;
  final void Function(String path) onDelete;

  String _size(Object? bytes) {
    final value = bytes is num ? bytes.toDouble() : 0.0;
    if (value < 1024) return value.round().toString() + ' Б';
    if (value < 1024 * 1024) return (value / 1024).round().toString() + ' КБ';
    return (value / (1024 * 1024)).toStringAsFixed(1) + ' МБ';
  }

  String _when(Object? ms) {
    final value = ms is num ? ms.toInt() : 0;
    if (value <= 0) return '';
    final d = DateTime.fromMillisecondsSinceEpoch(value);
    String two(int n) => n < 10 ? '0' + n.toString() : n.toString();
    return two(d.day) + '.' + two(d.month) + ' ' + two(d.hour) + ':' + two(d.minute);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: VVTheme.bg,
      appBar: AppBar(backgroundColor: VVTheme.surface, title: const Text('Записи на телефоне')),
      body: recordings.isEmpty
          ? const Padding(
              padding: EdgeInsets.all(24),
              child: Text(
                'Записей нет. Появятся здесь, если запись прервалась и не была разобрана.',
                style: TextStyle(color: VVTheme.inkMuted, height: 1.4),
              ),
            )
          : ListView.separated(
              padding: const EdgeInsets.all(16),
              itemCount: recordings.length,
              separatorBuilder: (_, __) => const SizedBox(height: 10),
              itemBuilder: (context, index) {
                final item = recordings[index];
                final path = (item['path'] ?? '').toString();
                return Container(
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(color: VVTheme.surface, borderRadius: BorderRadius.circular(14)),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        _when(item['modified_ms']) + ' · ' + _size(item['bytes']),
                        style: const TextStyle(fontWeight: FontWeight.w600),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        (item['name'] ?? '').toString(),
                        style: const TextStyle(color: VVTheme.inkMuted, fontSize: 12),
                      ),
                      const SizedBox(height: 10),
                      Row(
                        children: [
                          FilledButton(
                            onPressed: path.isEmpty ? null : () => onOpen(path),
                            child: const Text('Разобрать'),
                          ),
                          const SizedBox(width: 12),
                          TextButton(
                            onPressed: path.isEmpty ? null : () => onDelete(path),
                            child: const Text('Удалить'),
                          ),
                        ],
                      ),
                    ],
                  ),
                );
              },
            ),
    );
  }
}
