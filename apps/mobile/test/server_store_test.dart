import 'package:flutter_test/flutter_test.dart';
import 'package:v_voice/src/server_settings.dart';
import 'package:v_voice/src/server_store.dart';

ServerSettingsKeeper keeper(ServerStore store) => ServerSettingsKeeper(
      store: store,
      validate: ServerSettings.problem,
      normalize: ServerSettings.normalize,
    );

void main() {
  group('адрес без схемы не заставляет человека знать про http', () {
    test('«192.168.8.49:8000» без схемы получает https', () {
      expect(ServerSettings.normalize('192.168.8.49:8000'), 'https://192.168.8.49:8000');
    });

    test('явный http не переписывается', () {
      expect(ServerSettings.normalize('http://127.0.0.1:8000'), 'http://127.0.0.1:8000');
    });

    test('пустой адрес остаётся пустым, а не превращается в «https://»', () {
      expect(ServerSettings.normalize('   '), '');
    });
  });

  test('хороший адрес сохраняется нормализованным', () async {
    final store = MemoryServerStore();
    final reason = await keeper(store).save('https://v.ru/');
    expect(reason, isNull);
    expect(await store.read(), 'https://v.ru');
  });

  test('плохой адрес не сохраняется вовсе', () async {
    final store = MemoryServerStore();
    final reason = await keeper(store).save('v.ru');
    expect(reason, isNotNull);
    expect(await store.read(), isNull);
  });

  test('плохой адрес не затирает прежний хороший', () async {
    final store = MemoryServerStore('https://good.ru');
    final reason = await keeper(store).save('плохо');
    expect(reason, isNotNull);
    expect(await store.read(), 'https://good.ru');
  });

  test('после сохранения адрес читается при следующем запуске', () async {
    final store = MemoryServerStore();
    await keeper(store).save('https://v-voice.ru');
    expect(await keeper(store).load('https://fallback.ru'), 'https://v-voice.ru');
  });

  test('без сохранённого адреса берётся запасной', () async {
    expect(await keeper(MemoryServerStore()).load('https://fallback.ru/'), 'https://fallback.ru');
  });

  test('испорченное хранилище не ломает приложение', () async {
    final store = MemoryServerStore('мусор');
    expect(await keeper(store).load('https://fallback.ru'), 'https://fallback.ru');
  });

  test('сохранение дважды оставляет последнее значение', () async {
    final store = MemoryServerStore();
    await keeper(store).save('https://a.ru');
    await keeper(store).save('https://b.ru');
    expect(await store.read(), 'https://b.ru');
  });
}
