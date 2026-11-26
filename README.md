# v-voice — VoiceTranscribator («Умный диктофон»)

Слушает разговор, транскрибирует в реальном времени, отсекает шум и чужие голоса,
собирает задачи / встречи / напоминания и краткую выжимку. Ответ голосом не нужен —
**слушать и понимать**. Встраивается в задачник и CRM.

> Статус: **исследование и проектирование завершены**, ждём ответов на открытые вопросы.
> Дорожная карта и все задачи — в [Issues](https://github.com/dominumuniversi-cpu/v-voice/issues).

## Документы

| Документ | Что |
|---|---|
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
