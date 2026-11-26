import 'consent_model.dart';
import 'key_value_store.dart';

/// Сохранение согласия между запусками.
///
/// Почему не в памяти экрана: согласие, которое спрашивают при каждом пуске, люди перестают
/// читать — и тогда его как будто нет. При этом отзыв должен работать мгновенно, а смена
/// версии текста обязана обнулять принятое ранее.
class ConsentStore {
  ConsentStore({required this.store});

  static const String key = 'consent_version';

  final KeyValueStore store;

  /// Собирает модель с уже принятым согласием, если версия совпадает.
  Future<ConsentModel> load(ConsentModel base) async {
    final accepted = await store.read(key);
    if (accepted == null || accepted != base.version) {
      return base;
    }
    return base.accept();
  }

  Future<void> save(ConsentModel accepted) async {
    if (accepted.canRecord) {
      await store.write(key, accepted.version);
    } else {
      await store.remove(key);
    }
  }
}
