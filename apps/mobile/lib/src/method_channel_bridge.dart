import 'dart:async';

import 'package:flutter/services.dart';

import 'recording_controller.dart';

/// Реальный мост к нативной записи. Контракт тот же, что в Android и iOS:
/// канал `vvoice/recording` (start/stop/state) и `vvoice/recording/events` (поток событий).
class MethodChannelBridge implements RecordingBridge {
  MethodChannelBridge() {
    _events = _channel.receiveBroadcastStream().map((dynamic event) => Map<String, dynamic>.from(event as Map));
  }

  static const _channel = EventChannel('vvoice/recording/events');
  static const _method = MethodChannel('vvoice/recording');
  late final Stream<Map<String, dynamic>> _events;

  @override
  Stream<Map<String, dynamic>> get events => _events;

  @override
  Future<String> start() async {
    final result = await _method.invokeMethod<String>('start');
    return result ?? 'engine_failed';
  }

  @override
  Future<String> stop() async {
    final result = await _method.invokeMethod<String>('stop');
    return result ?? 'engine_failed';
  }

  /// Спрашиваем систему. Ошибку не выдаём за «всё хорошо»: неизвестность — это false,
  /// но решение принимает экран, а не этот метод.
  @override
  Future<bool> batteryRestricted() async {
    try {
      final result = await _method.invokeMethod<bool>('batteryRestricted');
      return result ?? false;
    } catch (_) {
      return false;
    }
  }

  @override
  Future<void> openBatterySettings() async {
    try {
      await _method.invokeMethod<String>('openBatterySettings');
    } catch (_) {
      // Экрана может не быть на прошивке; молчать здесь честнее, чем падать.
    }
  }
}
