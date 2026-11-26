@echo off
set DOCKER_HOST=tcp://localhost:2375
set DOCKER_CONFIG=C:\npc-docker-cfg
docker rm -f vv-probe >NUL 2>&1
docker run -d --name vv-probe -e VV_ASR_PROVIDER=speechmatics -e VV_ASR_KEY=wrong-key-check -e VV_LLM_PROVIDER=deepseek -e VV_LLM_KEY=wrong-llm-key -e VV_HOST=0.0.0.0 -e VV_DEVICE_TOKENS=k -p 18943:8080 -v E:\!Develop\Vernadsky\VoiceTranscribator\services\api:/app -w /app python:3.12-slim sh -c "python -m pip install -q -r requirements.txt; python main.py"