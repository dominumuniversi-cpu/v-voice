import 'dart:convert';

import 'package:http/http.dart' as http;

import 'api_client.dart';

/// Настоящий HTTP-транспорт поверх пакета http.
///
/// Здесь и только здесь приложение касается сети. Всё остальное (правила ответов, ошибки)
/// живёт в ApiClient и проверяется тестами без сети — так падение сети не делает приложение
/// непроверяемым.
class RealHttpTransport implements HttpTransport {
  RealHttpTransport({required this.baseUrl, http.Client? client, this.timeout = const Duration(seconds: 20)})
      : _client = client ?? http.Client();

  final String baseUrl;
  final http.Client _client;
  final Duration timeout;

  @override
  Future<(int, String)> get(String path) async {
    final response = await _client.get(Uri.parse(baseUrl + path)).timeout(timeout);
    // bytes + utf8: иначе русский текст в теле превращается в кракозябры
    return (response.statusCode, utf8.decode(response.bodyBytes));
  }

  @override
  Future<(int, String)> post(String path, Map<String, dynamic> body) async {
    final response = await _client
        .post(
          Uri.parse(baseUrl + path),
          headers: const {'Content-Type': 'application/json; charset=utf-8'},
          body: utf8.encode(jsonEncode(body)),
        )
        .timeout(timeout);
    return (response.statusCode, utf8.decode(response.bodyBytes));
  }

  void close() => _client.close();
}
