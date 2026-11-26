import 'api_client.dart';
import 'http_transport.dart';
import 'server_settings.dart';

/// Конфигурация приложения: адрес сервера и способ получить клиент API.
///
/// Одно место, где решается «куда стучимся». Экраны получают готовый ApiClient и не знают,
/// откуда взялся транспорт: тест подставит заглушку, продакшен — настоящий http.
class AppConfig {
  AppConfig({required this.serverUrl, this.deviceToken = '', HttpTransport? transport})
      : _transport = transport ?? RealHttpTransport(baseUrl: ServerSettings.normalize(serverUrl));

  /// Адрес по умолчанию: прод-сервер проекта. Меняется на экране настроек.
  static const String defaultServer = '';

  final String serverUrl;
  /// Токен устройства из настроек: сервер без него не пустит, если он не открыт.
  final String deviceToken;
  final HttpTransport _transport;

  ApiClient get api => ApiClient(
      transport: _transport,
      baseUrl: ServerSettings.normalize(serverUrl),
      deviceToken: deviceToken,
    );

  /// Проверка адреса: экран настроек показывает причину вместо «сервер недоступен».
  String? get addressProblem => ServerSettings.problem(serverUrl);
}
