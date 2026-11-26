# Отчёт вехи M0 — исследования и проектирование

Дата: 26.11.2026 · Репозиторий: [dominumuniversi-cpu/v-voice](https://github.com/dominumuniversi-cpu/v-voice)

## Что сделано

| Артефакт | Файл |
|---|---|
| ТЗ (FR-1…FR-31, AC-1…AC-10) | [docs/SPECS/VOICE-TZ.md](../SPECS/VOICE-TZ.md) |
| Архитектура | [docs/ARCHITECTURE/ARCHITECTURE.md](../ARCHITECTURE/ARCHITECTURE.md) |
| Подключение моделей | [docs/ARCHITECTURE/AI-PROVIDERS.md](../ARCHITECTURE/AI-PROVIDERS.md) |
| Исследование (факты + ссылки) | [docs/RESEARCH/RESEARCH-2026-11.md](../RESEARCH/RESEARCH-2026-11.md) |
| Дорожная карта M0–M6 | [docs/ROADMAP/ROADMAP.md](../ROADMAP/ROADMAP.md) |
| Вопросы владельцу | [docs/SPECS/QUESTIONS.md](../SPECS/QUESTIONS.md) |
| Дизайн (3 концепта + PNG) | [docs/UI/DESIGN.md](../UI/DESIGN.md), `docs/UI/prototypes/` |
| ADR-0001…0005 | `ADR/` |
| Бэклог | 29 issues, 7 milestones, 27 labels |

## Проверки (числа)

- Коммит `e44ad80`: 26 файлов, 1229 вставок; `git status` после — 0 строк.
- GitHub: default_branch = main, pushed 2026-11-26, issues = 29, milestones = 7.
- Скриншоты концептов: PNG 1000×980 отрендерены headless Chrome.

## Ограничения исследования (честно)

- `web_search` (DeepSeek API key), Tavily (403) и Serper недоступны → исследование велось прямой загрузкой
  официальных страниц через `web_fetch`; ссылки в документе есть, где не удалось получить — помечено.
- Официальные страницы Сбера (SaluteSpeech/GigaChat Audio) без JS не отдают текст — цены РФ-провайдеров
  **не подтверждены**, задача #26.

## Что дальше

1. Владелец отвечает на 5 ★-вопросов (issue #2) и выбирает дизайн (issue #4).
2. Старт S1 — Android-сервис записи (issue #5), параллельно S3 — сервер и ASR-адаптеры (issues #10, #11).
