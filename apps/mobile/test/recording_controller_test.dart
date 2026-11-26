import 'dart:async';

import 'package:flutter_test/flutter_test.dart';

import 'package:v_voice/src/recording_controller.dart';

/// Фейковый мост: повторяет контракт нативных реализаций, но без телефона.
class FakeBridge implements RecordingBridge {
  FakeBridge({this.startResult = 'ok'});

  final String startResult;
  final _events = StreamController<Map<String, dynamic>>.broadcast();
  int startCalls = 0;
  int stopCalls = 0;

  @override
  Stream<Map<String, dynamic>> get events => _events.stream;

  @override
  Future<String> start() async {
    startCalls++;
    return startResult;
  }

  @override
  Future<String> stop() async {
    stopCalls++;
    return 'ok';
  }

  void push(Map<String, dynamic> event) => _events.add(event);
  Future<void> close() => _events.close();
}

void main() {
  group('RecordingController', () {
    late FakeBridge bridge;
    late RecordingController controller;

    setUp(() {
      bridge = FakeBridge();
      controller = RecordingController(bridge)..bind();
    });

    tearDown(() async {
      await controller.dispose();
      await bridge.close();
    });

    test('старт переводит экран в состояние записи', () async {
      await controller.start();
      expect(controller.state, RecordingState.recording);
      expect(bridge.startCalls, 1);
    });

    test('двойное нажатие не создаёт вторую сессию', () async {
      await controller.start();
      await controller.start();
      expect(bridge.startCalls, 1);
    });

    test('отказ системы объясняется человеку и не оставляет «запись идёт»', () async {
      bridge = FakeBridge(startResult: 'not_allowed_in_background');
      controller = RecordingController(bridge)..bind();
      await controller.start();
      expect(controller.state, RecordingState.idle);
      expect(controller.lastError, contains('только с открытого экрана'));
    });

    test('стоп срабатывает сразу и без подтверждения', () async {
      await controller.start();
      await controller.stop();
      expect(controller.state, RecordingState.stopped);
      expect(bridge.stopCalls, 1);
    });

    test('живой текст приходит событиями моста, без опроса', () async {
      bridge.push({'type': 'live', 'value': 'Я отправлю смету'});
      await Future<void>.delayed(Duration.zero);
      expect(controller.liveText, 'Я отправлю смету');
    });

    test('обрыв связи с нативной частью виден на экране, а не проглатывается', () async {
      controller.bind();
      await bridge.close();
      await Future<void>.delayed(Duration.zero);
      expect(controller.state, RecordingState.unavailable);
      expect(controller.lastError, isNotEmpty);
    });
  });
}
