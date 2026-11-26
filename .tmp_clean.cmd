@echo off
set DOCKER_HOST=tcp://localhost:2375
set DOCKER_CONFIG=C:\npc-docker-cfg
docker rm -f vv-probe >NUL 2>&1