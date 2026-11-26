# v-voice — VoiceTranscribator («Умный диктофон»)

Слушает разговор, транскрибирует в реальном времени, отсекает шум и чужие голоса,
собирает задачи / встречи / напоминания и краткую выжимку. Ответ голосом не нужен —
**слушать и понимать**. Встраивается в задачник и CRM.

> Статус: **работающий код, а не только документы.** APK собирается в CI, 76 Flutter-тестов,
> 174 серверных проверки, 10 тестов нативного контракта. Живого прогона на телефоне ещё не было —
> он ждёт ответов владельца ([#36](https://github.com/dominumuniversi-cpu/v-voice/issues/36)) и устройств.
> Все задачи — в [Issues](https://github.com/dominumuniversi-cpu/v-voice/issues), дорожная карта — в вехах.
> Дорожная карта и все задачи — в [Issues](https://github.com/dominumuniversi-cpu/v-voice/issues).

| `docs/SPECS/ISSUE-SPEC.md` | как заводить задачи в задачнике репозитория |
| `docs/REPORTS/` | отчёты вех с числами проверок |

## Документы

| Документ | Что |
|---

## Что уже работает и что нет

| Уже работает | Где |
|---|---|
| Запись в фоне на Android, индикатор уровня, метки, часы | `apps/mobile/` + `android/` |
| Согласие на запись до старта, сохраняется между запусками | `lib/src/consent_model.dart`, `consent_store.dart` |
| Разбор: правило «нет цитаты — нет задачи», отсечение чужих голосов | `services/api/vvoice/evidence.py` |
| Выжимка, формат TXT/MD/SRT/VTT/JSON, выгрузка в задачник и CRM | `digest.py`, `formats.py`, `exporters.py` |
| Проверка ключей моделей, лимиты, восстановление записи после сбоя | `provider_probe.py`, `limits.py`, `recovery.py` |
| Сборка APK в CI на каждый коммит | `.github/workflows/ci.yml` |

| Ещё нет | Почему |
|---|---|
| Живой прогон на телефоне | нет устройств; нужен ответ владельца |
| Сборка iOS | нужен macOS-раннер — [#35](https://github.com/dominumuniversi-cpu/v-voice/issues/35) |
| Свой сервер для распознавания (GigaAM) | нужна GPU |
| Настоящий поток живого текста с сервера | ждёт адрес сервера (вопрос в [#36](https://github.com/dominumuniversi-cpu/v-voice/issues/36)) |

---|---|
| [ТЗ](docs/SPECS/VOICE-TZ.md) | FR-1…FR-31, AC-1…AC-10, out of scope |
| [Архитектура](docs/ARCHITECTURE/ARCHITECTURE.md) | конвейер, API v1, модель данных, ограничения платформ |
| [Подключение моделей](docs/ARCHITECTURE/AI-PROVIDERS.md) | какие модели, env, как подключать руками |
| [Исследование](docs/RESEARCH/RESEARCH-2026-11.md) | факты со ссылками: iOS/Android фон, ASR, цены |
| [Дорожная карта](docs/ROADMAP/ROADMAP.md) | M0–M6, спринты S0–S8 |
| [Вопросы владельцу](docs/SPECS/QUESTIONS.md) | 5 блокирующих вопросов до старта кода |
| [Дизайн](docs/UI/DESIGN.md) | три концепта: A Deep Focus, B Paper Desk, C Signal |
| [ADR](ADR/README.md) | принятые архитектурные решения |

## Дизайн-концепты

- A «Deep Focus» — `docs/UI/prototypes/concept-a-deep-focus.html` + `.png`
- B «Paper Desk» — `docs/UI/prototypes/concept-b-paper-desk.html` + `.png`
- C «Signal» — `docs/UI/prototypes/concept-c-signal.html` + `.png`

## Быстрый вывод по платформам

| Платформа | Запись при заблокированном экране |
|---|---|
| Android 14+ | **Работает** через foreground-сервис типа `microphone` (старт только из видимого UI). |
| iOS | **Не гарантировано**: режим `audio` у Apple описан как *воспроизведение звука*; держим буфер и честно показываем статус. |

Подробно — [RESEARCH §1](docs/RESEARCH/RESEARCH-2026-11.md).
