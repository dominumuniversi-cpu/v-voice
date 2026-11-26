import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:v_voice/src/api_client.dart';
import 'package:v_voice/src/audio_file.dart';

class _Fake implements HttpTransport {
  _Fake(this.reply);
  final (int, String) reply;
  Map<String, dynamic>? lastBody;

  @override
  Future<(int, String)> get(String path) async => reply;

  @override
  Future<(int, String)> post(String path, Map<String, dynamic> body) async {
    lastBody = body;
    return reply;
  }
}

void main() {
  group('загрузка записи', () {
    test('успех возвращает идентификатор сессии', () async {
      final t = _Fake((200, '{"session_id":"abc123def456"}'));
      final api = ApiClient(transport: t, baseUrl: '');
      final id = await api.uploadSession([1, 2, 3]);
      expect(id, 'abc123def456');
      expect(t.lastBody!['audio_base64'], isNotNull);
    });

    test('отказ сервера объясняет причину', () async {
      final api = ApiClient(
        transport: _Fake((415, '{"error":"not_wav","message":"Нужен файл WAV: заголовок не распознан."}')),
        baseUrl: '',
      );
      expect(await api.uploadSession([1, 2, 3]), isNull);
      expect(api.lastUploadProblem, contains('WAV'));
    });

    test('пустая запись не отправляется вообще', () async {
      final t = _Fake((200, '{"session_id":"x"}'));
      final api = ApiClient(transport: t, baseUrl: '');
      expect(await api.uploadSession([]), isNull);
      expect(t.lastBody, isNull);
      expect(api.lastUploadProblem, contains('пустая'));
    });
  });

  group('запуск разбора', () {
    test('успешный запуск не оставляет причины отказа', () async {
      final api = ApiClient(transport: _Fake((200, '{"summary":[]}')), baseUrl: '');
      expect(await api.startAnalysis('abc123def456'), isTrue);
      expect(api.lastAnalysisProblem, isEmpty);
    });

    test('отказ сервера объясняет причину, а не молчит', () async {
      final api = ApiClient(
        transport: _Fake((503, '{"error":"pipeline_unavailable","message":"Сервер не настроен запускать разбор."}')),
        baseUrl: '',
      );
      expect(await api.startAnalysis('abc123def456'), isFalse);
      expect(api.lastAnalysisProblem, contains('не настроен'));
    });

    test('404 не считается успехом', () async {
      final api = ApiClient(
        transport: _Fake((404, '{"error":"session_not_found"}')),
        baseUrl: '',
      );
      expect(await api.startAnalysis('abc123def456'), isFalse);
      expect(api.lastAnalysisProblem, isNotEmpty);
    });
  });

  group('живой текст', () {
    test('сессия открывается до записи', () async {
      final api = ApiClient(transport: _Fake((200, '{"session_id":"abcdef1234567890"}')), baseUrl: '');
      expect(await api.openSession(), 'abcdef1234567890');
    });

    test('кусок звука возвращает накопленный текст', () async {
      final api = ApiClient(transport: _Fake((200, '{"text":"Я отправлю смету"}')), baseUrl: '');
      expect(await api.sendLiveChunk('abcdef1234567890', [1, 2, 3]), 'Я отправлю смету');
      expect(api.lastLiveProblem, isEmpty);
    });

    test('пустой ответ сервера не затирает показанный текст', () async {
      final api = ApiClient(transport: _Fake((200, '{"text":""}')), baseUrl: '');
      expect(await api.sendLiveChunk('abcdef1234567890', [1, 2, 3]), isNull);
    });

    test('пустой кусок не отправляется', () async {
      final t = _Fake((200, '{"text":"x"}'));
      final api = ApiClient(transport: t, baseUrl: '');
      expect(await api.sendLiveChunk('abcdef1234567890', []), isNull);
      expect(t.lastBody, isNull);
    });
  });

  group('чтение записи с диска', () {
    test('пустой путь — ошибка, а не пустая отправка', () async {
      expect(() => readFileBytes(''), throwsA(isA<FormatException>()));
    });

    test('несуществующий файл — ошибка с путём', () async {
      expect(() => readFileBytes('/нет/такого/файла.wav'), throwsA(isA<FileSystemException>()));
    });

    test('настоящий файл читается целиком', () async {
      final dir = await Directory.systemTemp.createTemp('vvoice');
      final file = File(dir.path + '/a.wav');
      await file.writeAsBytes([82, 73, 70, 70]);
      expect(await readFileBytes(file.path), [82, 73, 70, 70]);
      await dir.delete(recursive: true);
    });
  });
}
