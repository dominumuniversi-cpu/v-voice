import 'dart:io';
import 'dart:typed_data';

/// Читает запись с диска.
///
/// Отдельная функция: экран не знает про файловую систему, а тесты подменяют чтение
/// без настоящего диска. Пустой файл — это ошибка, а не «отправлено успешно».
Future<Uint8List> readFileBytes(String path) async {
  if (path.trim().isEmpty) {
    throw const FormatException('Путь к записи пуст.');
  }
  final file = File(path);
  if (!await file.exists()) {
    throw FileSystemException('Запись не найдена', path);
  }
  final bytes = await file.readAsBytes();
  if (bytes.isEmpty) {
    throw const FormatException('Файл записи пуст.');
  }
  return bytes;
}
