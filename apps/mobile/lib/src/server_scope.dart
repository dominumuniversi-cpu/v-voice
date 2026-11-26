import 'package:flutter/material.dart';

import 'first_run_screen.dart';
import 'theme.dart';

import 'app_config.dart';
import 'server_settings.dart';
import 'server_store.dart';

/// Адрес сервера, который действует прямо сейчас.
///
/// Зачем: настройка на экране не имела смысла, пока экраны создавали клиент с адресом по умолчанию.
/// Здесь одно место правды: человек сохранил адрес — все экраны работают с ним, без перезапуска.
class ServerScope extends InheritedWidget {
  const ServerScope({
    super.key,
    required this.serverUrl,
    this.deviceToken = '',
    required this.onChanged,
    required super.child,
  });

  /// Действующий адрес (уже нормализован).
  final String serverUrl;

  /// Токен устройства. Пустой — сервер открыт (режим разработки).
  final String deviceToken;

  /// Смена адреса: сохраняет и перерисовывает всех, кто читает адрес.
  final Future<void> Function(String) onChanged;

  static ServerScope? maybeOf(BuildContext context) => context.dependOnInheritedWidgetOfExactType<ServerScope>();

  /// Клиент API с действующим адресом. Тесты подменяют транспорт внутри AppConfig.
  AppConfig get config => AppConfig(serverUrl: serverUrl, deviceToken: deviceToken);

  @override
  bool updateShouldNotify(ServerScope oldWidget) =>
      oldWidget.serverUrl != serverUrl || oldWidget.deviceToken != deviceToken;
}

/// Загрузка сохранённого адреса при старте: первое, что делает приложение.
///
/// Пока адрес читается, показывается пустой экран — это доли секунды и честнее, чем
/// один такт работать с неверным адресом.
class ServerScopeLoader extends StatefulWidget {
  const ServerScopeLoader({
    super.key,
    required this.store,
    this.tokenStore,
    required this.child,
  });

  final ServerStore store;

  /// Где лежит токен устройства. Не задан — токена нет (так работают тесты).
  final ServerStore? tokenStore;
  final Widget Function(BuildContext context) child;

  @override
  State<ServerScopeLoader> createState() => _ServerScopeLoaderState();
}

class _ServerScopeLoaderState extends State<ServerScopeLoader> {
  String? _url;
  String _token = '';

  /// Та же связка правил, что и на экране настроек: одно место проверки адреса.
  ServerSettingsKeeper get _keeper => ServerSettingsKeeper(
        store: widget.store,
        validate: ServerSettings.problem,
        normalize: ServerSettings.normalize,
      );

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final keeper = _keeper;
    final url = await keeper.load(AppConfig.defaultServer);
    final token = (await widget.tokenStore?.read()) ?? '';
    if (mounted) {
      setState(() {
        _url = url;
        _token = token;
      });
    }
  }

  Future<void> _change(String next) async {
    final normalized = ServerSettings.normalize(next);
    await _keeper.save(normalized);
    if (mounted) setState(() => _url = normalized);
  }

  @override
  Widget build(BuildContext context) {
    final url = _url;
    if (url == null) {
      return const ColoredBox(color: VVTheme.bg);
    }
    // Адреса ещё нет — приложение не должно молча ходить в выдуманный домен и показывать
    // «сервер не ответил». Первый шаг человека — выбрать адрес, и он делается сразу.
    if (url.isEmpty) {
      return FirstRunScreen(onSaved: (raw) => _change(raw));
    }
    return ServerScope(
      serverUrl: url,
      deviceToken: _token,
      onChanged: _change,
      child: widget.child(context),
    );
  }
}
