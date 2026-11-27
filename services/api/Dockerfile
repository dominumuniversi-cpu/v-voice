# Стенд v-voice: сервер записи и разбора.
# Наружу порт НЕ публикуется: nginx маршрутизирует /voice/ на voice-app:8080 внутри npc-proxy-net.
FROM python:3.12-slim

WORKDIR /app

# Зависимости ставятся при сборке: если делать это на старте, сервис поднимается ~минуту и
# liveness-проверки успевают убить его раньше, чем он ответит.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV VV_HOST=0.0.0.0 \
    VV_PORT=8080 \
    PYTHONUNBUFFERED=1

EXPOSE 8080

# -u: без него stdout буферизуется и журнал в docker logs пуст.
CMD ["python", "-u", "main.py"]
