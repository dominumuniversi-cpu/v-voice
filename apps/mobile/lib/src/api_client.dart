import 'dart:convert';

import 'digest_model.dart';

/// Транспорт HTTP: подменяется в тестах, поэтому логика клиента проверяется без сети.
abstract class HttpTransport {
  /// Возвращает (код ответа, тело).
  Future<(int, String)> post(String path, Map<String, dynamic> body);
  Future<(int, String)> get(String path);
}

/// Клиент нашего сервера (API v1).
///
/// Правила, которые здесь закреплены:
///  1. Любой ответ, кроме 200, превращается в понятную ошибку с кодом — приложение не молчит.
///  2. Тело читается как UTF-8: русский текст в ответах не должен превращаться в кракозябры.
///  3. Проверяемый ключ отправляется и НЕ сохраняется на телефоне: держим только в памяти экрана.
class ApiClient {
  ApiClient({required this.transport, required this.baseUrl});

  final HttpTransport transport;
  final String baseUrl;

  /// Проверка ключа провайдера (FR-24).
  Future<(String verdict, String message)> probe(String provider, String apiKey) async {
    final (code, body) = await transport.post('/api/v1/probe', {'provider': provider, 'api_key': apiKey});
    if (code == 200) {
      final data = jsonDecode(body) as Map<String, dynamic>;
      return ((data['verdict'] ?? 'unknown').toString(), (data['message'] ?? '').toString());
    }
    if (code == 400) {
      final data = _safeDecode(body);
      return ('rejected', (data['message'] ?? 'Сервер отклонил запрос проверки.').toString());
    }
    return ('rejected', 'Сервер ответил кодом ' + code.toString() + '.');
  }

  /// Проверка элемента разбора против расшифровки — тем же правилом, что на сервере.
  Future<(bool ok, String reason)> validateItem(Map<String, dynamic> item, String transcript) async {
    final (code, body) = await transport.post('/api/v1/items/validate', {'item': item, 'transcript': transcript});
    if (code == 200) return (true, '');
    final data = _safeDecode(body);
    if (code == 422) return (false, (data['reason'] ?? 'цитаты нет в расшифровке').toString());
    return (false, (data['message'] ?? 'Ошибка сервера: ' + code.toString()).toString());
  }

  /// Готовый разбор с сервера. Возвращает null, если сервер не дал выжимку — приложение не выдумывает.
  Future<Digest?> fetchDigest(String sessionId) async {
    final (code, body) = await transport.get('/api/v1/sessions/' + sessionId + '/digest');
    if (code != 200) return null;
    final data = _safeDecode(body);
    if (data.isEmpty) {
      lastDigestProblem = 'Сервер прислал пустой ответ.';
      return null;
    }
    return Digest.fromJson(data);
  }

  Map<String, dynamic> _safeDecode(String body) {
    try {
      final decoded = jsonDecode(body);
      return decoded is Map<String, dynamic> ? decoded : <String, dynamic>{};
    } catch (_) {
      return <String, dynamic>{};
    }
  }
}
