# AGENTS.md — VoiceTranscribator (v-voice)

Проект: **«Умный диктофон»** — непрерывная запись и онлайн-транскрибация голоса, осмысленный разбор
разговора (задачи/встречи/напоминания) и краткая выжимка. Без голосового ответа — только «слышать и понимать».

## Обязательно прочитать до любой работы

1. Глобальные правила DSH читаются автоматически (`$DSH_HOME\AGENTS.md`: служба, модели, обмен JSON-конвертами, стенды, секреты, безопасный код). Манифесты группы проектов `E:\!Develop\Vernadsky\General rules\` — только по триггеру, когда речь именно о них: `DEV-RULES.md` (общие правила разработки), `SDD.md` (Spec → Plan → Tasks → Code), `SESSIONS.md`, `SWARM.md`, `TOKENS.md`, `HOSTING.md`.
2. Локальные правила проекта: `docs/SPECS/LOCAL-RULES.md`.
3. Текущее состояние: `docs/ROADMAP/ROADMAP.md`, `docs/SPECS/STATUS.md`.
4. Шаблон задачи: `docs/SPECS/ISSUE-SPEC.md`. Задачник — GitHub Issues репозитория `dominumuniversi-cpu/v-voice`. Все задачи/баги — только там.

## Правила этого проекта

- **Spec → Plan → Tasks → Code** (SDD.md). Спецификация первична, код — производное.
- Состояние живёт в файлах. Решение не записано — его не существует.
- Все задачи, баги, бэклоги — в GitHub Issues (метки `area/*`, `type/*`, `phase/*`, `p0..p3`,
  `mobile`, `backend`, `ai`, `design`, `research`). Дорожная карта = GitHub Milestones.
- Временные файлы — только `.tmp/` внутри проекта; в корне и в git их быть не должно.
- Секреты — никогда в репозитории. Ключи моделей — через env/файл вне git (`secrets/`, gitignore).
- Коммиты: Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`, `test:`), латиница, строчные.
- Ветки: `feat/*`, `fix/*`, `docs/*` — kebab-case, от актуального main, одна тема.

## Карта документов

| Файл | Что внутри |
|---|---|
| `docs/SPECS/VOICE-TZ.md` | основной ТЗ (FR, AC, out of scope) |
| `docs/SPECS/LOCAL-RULES.md` | локальные правила проекта (порты, стек, схема БД) |
| `docs/ARCHITECTURE/ARCHITECTURE.md` | архитектура и конвейер |
| `docs/ARCHITECTURE/EXPORT-CONTRACT.md` | контракт `vvoice.item.v1` для внешних продуктов (задачник, CRM) |
| `docs/ARCHITECTURE/AI-PROVIDERS.md` | какие модели/провайдеры подключать и как |
| `docs/RESEARCH/RESEARCH-2026-11.md` | обзор решений, сравнение сервисов и библиотек |
| `docs/ARCHITECTURE/STAND.md` | стенд /voice/ на DIMAS: адрес, токен, пересборка, ловушки nginx |
| `docs/ARCHITECTURE/LIVE-RUN.md` | живой прогон без ключей (демо-режим), порт, токен, маршрут, ожидаемое |
| `docs/ROADMAP/ROADMAP.md` | дорожная карта и связь с issues/milestones |
| `docs/UI/DESIGN.md` | UI-канон, дизайн-концепции, шаблоны |
| `ADR/` | архитектурные решения |
