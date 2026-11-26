import 'package:flutter/material.dart';

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
    required this.onChanged,
    required super.child,
  });

  /// Действующий адрес (уже нормализован).
  final String serverUrl;

  /// Смена адреса: сохраняет и перерисовывает всех, кто читает адрес.
  final Future<void> Function(String) onChanged;

  static ServerScope? maybeOf(BuildContext context) => context.dependOnInheritedWidgetOfExactType<ServerScope>();

  /// Клиент API с действующим адресом. Тесты подменяют транспорт внутри AppConfig.
  AppConfig get config => AppConfig(serverUrl: serverUrl);

  @override
  bool updateShouldNotify(ServerScope oldWidget) => oldWidget.serverUrl != serverUrl;
}

/// Загрузка сохранённого адреса при старте: первое, что делает приложение.
///
/// Пока адрес читается, показывается пустой экран — это доли секунды и честнее, чем
/// один такт работать с неверным адресом.
class ServerScopeLoader extends StatefulWidget {
  const ServerScopeLoader({
    super.key,
    required this.store,
    required this.child,
  });

  final ServerStore store;
  final Widget Function(BuildContext context) child;

  @override
  State<ServerScopeLoader> createState() => _ServerScopeLoaderState();
}

class _ServerScopeLoaderState extends State<ServerScopeLoader> {
  String? _url;

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
    if (mounted) setState(() => _url = url);
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
      return const ColoredBox(color: Color(0xFF0B0F14));
    }
    return ServerScope(
      serverUrl: url,
      onChanged: _change,
      child: widget.child(context),
    );
  }
}
