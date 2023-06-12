FROM python:3.9.17-slim-bullseye

ENV SERVER_IP="127.0.0.1"

WORKDIR /usr/src/app

COPY worker.py ./worker.py

COPY requirements*.txt ./

RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements_torch.txt && \
    pip install --no-cache-dir -r requirements_demucs.txt && \
    pip install --no-cache-dir -r requirements_api.txt

RUN apt-get update && \
    apt-get install ffmpeg -y

ENTRYPOINT python worker.py -server ${SERVER_IP}