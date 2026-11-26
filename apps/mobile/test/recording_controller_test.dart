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

    test('уровень микрофона доходит до экрана', () async {
      await controller.start();
      bridge.push({'type': 'level', 'value': 0.42});
      await Future<void>.delayed(Duration.zero);
      expect(controller.level, closeTo(0.42, 0.001));
    });

    test('уровень обрезается в границах 0..1', () async {
      await controller.start();
      bridge.push({'type': 'level', 'value': 2.5});
      await Future<void>.delayed(Duration.zero);
      expect(controller.level, 1.0);
      bridge.push({'type': 'level', 'value': -0.3});
      await Future<void>.delayed(Duration.zero);
      expect(controller.level, 0.0);
    });

    test('мусор вместо уровня не роняет поток событий', () async {
      await controller.start();
      bridge.push({'type': 'level', 'value': 'громко'});
      await Future<void>.delayed(Duration.zero);
      expect(controller.level, 0.0);
      expect(controller.state, RecordingState.recording);
    });

    test('кусок звука доходит и не копится', () async {
      await controller.start();
      bridge.push({'type': 'audio', 'pcm': [1, 2, 3, 4]});
      bridge.push({'type': 'audio', 'pcm': [5, 6]});
      await Future<void>.delayed(Duration.zero);
      expect(controller.audioChunksReceived, 2);
      // Хранится только последний кусок: память не растёт с длиной разговора.
      expect(controller.lastAudioChunk, [5, 6]);
    });

    test('пустой кусок звука не считается', () async {
      await controller.start();
      bridge.push({'type': 'audio', 'pcm': <int>[]});
      await Future<void>.delayed(Duration.zero);
      expect(controller.audioChunksReceived, 0);
    });

    test('путь к записи доходит до экрана', () async {
      await controller.start();
      bridge.push({'type': 'saved', 'path': '/data/seg/segment.wav', 'duration_ms': 12000});
      await Future<void>.delayed(Duration.zero);
      expect(controller.lastSavedPath, '/data/seg/segment.wav');
      expect(controller.lastDurationMs, 12000);
    });

    test('пустое событие не затирает сохранённый путь', () async {
      await controller.start();
      bridge.push({'type': 'saved', 'path': '/data/a.wav', 'duration_ms': 1000});
      await Future<void>.delayed(Duration.zero);
      bridge.push({'type': 'saved', 'path': ''});
      await Future<void>.delayed(Duration.zero);
      expect(controller.lastSavedPath, '/data/a.wav');
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
      await controller.start();
      await bridge.close();
      await Future<void>.delayed(const Duration(milliseconds: 50));
      expect(controller.state, RecordingState.unavailable);
      expect(controller.lastError, isNotEmpty);
    });
  });

  test('RecordingController кончившееся место объясняется человеку', () {
    // Проверка на смысл: при переполнении диска человек должен понять, что запись остановлена
    // и что уже записанное сохранено — иначе он будет ждать несуществующий файл.
    final text = RecordingController.explain('disk_full');
    expect(text.contains('место'), isTrue, reason: text);
    expect(text.contains('остановлена'), isTrue, reason: text);
  });

  test('RecordingController прерывание звонком объясняется человеку', () {
    final text = RecordingController.explain('recording_interrupted');
    expect(text.contains('прервана'), isTrue, reason: text);
  });
}
