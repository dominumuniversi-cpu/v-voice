# Отчёт спринта M1 — нативные мосты и конвейер

Дата: 26.11.2026 · Коммиты: `e44ad80`, `752b645`, `26318ab` · CI: [.github/workflows/ci.yml](../.github/workflows/ci.yml)

## Что сделано в этом отчёте

| Слой | Файлы | Что доказано |
|---|---|---|
| Android | `apps/mobile/android/app/src/main/kotlin/ru/vernadsky/vvoice/` | foreground-сервис типа microphone, старт только из UI, файл на диск каждые ~200 мс, WAV-заголовок восстанавливается после падения |
| iOS | `apps/mobile/ios/Runner/` | AVAudioSession .playAndRecord + UIBackgroundModes audio, сегменты на диск, background task для досылки |
| Контроль расхождений | `tests/native/contract.json` + `native-drift-check.mjs` | «нет foregroundServiceType=microphone» и «нет UIBackgroundModes» ловятся тестом |
| Конвейер | `services/api/vvoice/` | шум и тишина отсеиваются до отправки; volatile не попадает в разбор; обрыв провайдера не теряет полученное |
| Правило цитат | `evidence.py` + `tests/api/` | выдуманная задача, короткая цитата, цитата из другой встречи — отбрасываются |
| members_only | `evidence.py`, `digest.py`, ТЗ § | «слышим всех — разбираем участников»: задача чужого голоса не доезжает в задачник, аудио остаётся |

## Проверки (числа)

- `npm run check`: **14 тестов, 14 pass, 0 fail**.
- `node scripts/syntax-check.mjs`: **10 python-файлов**, 0 проблем; проверка ловит несбалансированные скобки (проверено на намеренно сломанном файле).
- Коммит `26318ab`: **33 файла, 1647 вставок**.
- Issues: было 29 → стало **34** (добавлены угловые случаи).

## Чего НЕ проверено (честно)

- **Streaming** на natives ещё не собран: нужен Flutter SDK и телефон (нет на этой машине).
- **Python-тесты не запускались** (Python не установлен в этой среде); готов pytest-файл и чистая проверка
  без pytest — прогонятся в CI.
- Задержка < 1 с и непрерывность фона на живых устройствах — требуют телефонов.
