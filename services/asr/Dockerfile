# Своё распознавание речи: открытая модель на процессоре, бесплатно, без ключей и облака.
FROM python:3.12-slim

ENV ASR_MODEL=small ASR_DEVICE=cpu ASR_COMPUTE=int8 ASR_LANGUAGE=ru ASR_MODEL_DIR=/models
RUN pip install --no-cache-dir faster-whisper==1.1.1 requests==2.32.3 huggingface_hub==0.26.2

WORKDIR /app
COPY server.py /app/server.py

EXPOSE 8090
CMD ["python", "/app/server.py"]
