import 'package:flutter_test/flutter_test.dart';
import 'package:v_voice/src/consent_model.dart';
import 'package:v_voice/src/consent_store.dart';
import 'package:v_voice/src/key_value_store.dart';

ConsentModel base([String version = 'v1']) =>
    ConsentModel(version: version, terms: const ['Приложение слушает разговор']);

void main() {
  test('свежая установка: согласия нет', () async {
    final store = ConsentStore(store: MemoryKeyValueStore());
    expect((await store.load(base())).canRecord, isFalse);
  });

  test('сохранённое согласие поднимается при следующем запуске', () async {
    final kv = MemoryKeyValueStore();
    final store = ConsentStore(store: kv);
    await store.save(base().accept());
    expect((await store.load(base())).canRecord, isTrue);
  });

  test('новая версия текста не засчитывается старым согласием', () async {
    final kv = MemoryKeyValueStore();
    final store = ConsentStore(store: kv);
    await store.save(base('v1').accept());
    expect((await store.load(base('v2'))).canRecord, isFalse);
  });

  test('отзыв согласия стирает запись', () async {
    final kv = MemoryKeyValueStore();
    final store = ConsentStore(store: kv);
    await store.save(base().accept());
    await store.save(base().revoke());
    expect(await kv.read(ConsentStore.key), isNull);
    expect((await store.load(base())).canRecord, isFalse);
  });

  test('чужая версия в хранилище не считается согласием', () async {
    final kv = MemoryKeyValueStore();
    await kv.write(ConsentStore.key, 'v0');
    expect((await ConsentStore(store: kv).load(base())).canRecord, isFalse);
  });
}
