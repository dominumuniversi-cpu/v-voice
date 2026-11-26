# Живой прогон без ключей (демо-режим)

Проверка поведения «как у человека», когда реальных ключей ASR/LLM нет. Тесты и гайды такое не ловят:
они видят код, а не то, что приходит на телефон.

## Рецепт

```cmd
set DOCKER_HOST=tcp://localhost:2375
set DOCKER_CONFIG=C:\npc-docker-cfg

docker run -d --name vv-live ^
  -v "<путь к репозиторию>\services\api:/app" -w /app ^
  -e VV_HOST=0.0.0.0 -e VV_DEVICE_TOKENS=k ^
  -e VV_ASR_PROVIDER=fake -e VV_LLM_PROVIDER=fake ^
  python:3.12-slim sh -c "python main.py"
```

Готовность — примерно через 50–70 секунд после старта (Python 3.12 slim качает зависимости не сам:
если образа нет локально, `docker pull python:3.12-slim` нужен заранее).

## Три ловушки, на которые я уже наступал

| Ловушка | Что было | Правильно |
|---|---|---|
| Порт | пробовал 8000 | сервер слушает **8080** (`VV_PORT`, по умолчанию 8080) |
| Токен | получил `401 Unauthorized` | при `VV_DEVICE_TOKENS` каждый запрос несёт заголовок `Authorization: Bearer k` |
| Форма ответа | `/digest` отдавал обёртку | с коммита `5da6291` разбор лежит сверху, реплики рядом |

## Минимальный маршрут

1. `POST /api/v1/sessions` с `{"audio_base64": "<wav>"}` → `session_id`.
2. `POST /api/v1/sessions/<id>/analyze` → 200, разбор посчитан.
3. `GET /api/v1/sessions/<id>/digest` → в ответе `summary`, `items`, `utterances`.
4. `GET /api/v1/sessions/<id>/transcript?format=srt` → файл субтитров.

## Ожидаемое в демо-режиме

- Синтетический тон VAD справедливо отсекает: `sent_seconds` может быть 0, а `dropped_by_vad` — расти.
  Это не дефект, а работа фильтра.
- Заглушка модели даёт 1 задачу из демо-фразы `я отправлю смету завтра утром, созвонимся в четверг`.

## Уборка

```cmd
docker rm -f vv-live
```

Контейнер без `--rm` намеренно: после падения его логи нужны для разбора.
