import 'package:flutter_test/flutter_test.dart';
import 'package:v_voice/src/consent_model.dart';

ConsentModel fresh({String? accepted}) => ConsentModel(
      version: '2026-11-01',
      terms: const ['Приложение слушает разговор', 'Текст хранится на вашем сервере'],
      acceptedVersion: accepted,
    );

void main() {
  group('согласие на запись', () {
    test('без согласия запись закрыта', () {
      expect(fresh().canRecord, isFalse);
    });

    test('после принятия текущей версии запись открыта', () {
      expect(fresh().accept().canRecord, isTrue);
    });

    test('новая версия текста сбрасывает согласие', () {
      final accepted = fresh().accept();
      expect(accepted.canRecord, isTrue);
      final updated = ConsentModel(version: '2026-12-01', terms: accepted.terms, acceptedVersion: accepted.acceptedVersion);
      expect(updated.canRecord, isFalse);
    });

    test('отзыв согласия снова закрывает запись', () {
      expect(fresh().accept().revoke().canRecord, isFalse);
    });

    test('принятие другой версии не считается принятием текущей', () {
      expect(fresh(accepted: '2025-01-01').canRecord, isFalse);
    });

    test('текст согласия не пустой — иначе это не согласие', () {
      expect(fresh().terms, isNotEmpty);
      for (final line in fresh().terms) {
        expect(line.trim(), isNotEmpty);
      }
    });

    test('человеку объяснено, почему кнопка не работает', () {
      expect(ConsentModel.blockMessage, contains('разговор'));
      expect(ConsentModel.blockMessage.length, greaterThan(40));
    });
  });
}
