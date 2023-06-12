#!/bin/bash

# sudo ./run_server.sh [--init]

echo -e "[-] Cleaning all received and produced files"
sudo rm -r uploads
sudo rm -r download

echo -e "[-] Cleaning rabbitmq channels..." 
sudo rabbitmqctl purge_queue job_queue &>/dev/null
sudo rabbitmqctl purge_queue result_queue &>/dev/null

echo "[+] Creating environment..."
python3 -m venv venv    &>/dev/null
source venv/bin/activate    &>/dev/null

if [[ $1 == "--init" ]];then
    echo "[+] Installing dependencies..."
    sudo apt-get update &>/dev/null
    sudo apt install ffmpeg &>/dev/null
    sudo apt-get install rabbitmq-server -y --fix-missing &>/dev/null
    sudo systemctl start rabbitmq-server &>/dev/null

    echo "[+] Installing pip dependencies"
    pip install pip --upgrade &>/dev/null
    pip install -r requirements_torch.txt &>/dev/null
    pip install -r requirements_demucs.txt &>/dev/null
    pip install -r requirements_api.txt &>/dev/null

    echo "[+] Starting rabbitmq server..."
    sudo rabbitmq-server start -detached & 
    sleep 2
fi

echo "[+] Starting API at 0.0.0.0:8000..."
python3 api.py

echo -e "[-] Cleaning all received and produced files"
sudo rm -r uploads
sudo rm -r download