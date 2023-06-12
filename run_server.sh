#!/bin/bash

# sudo ./run_server.sh [--init]

echo -e "\n[-] Cleaning all received and produced files"
sudo rm -r uploads
sudo rm -r download

echo -e "\n[-] Cleaning rabbitmq channels..." 
sudo rabbitmqctl purge_queue job_queue
sudo rabbitmqctl purge_queue result_queue

echo -e "\n[+] Creating environment..."
sudo apt install python3.11-venv -y
python3 -m venv venv
source venv/bin/activate

if [[ $1 == "--init" ]];then
    echo -e "\n[+] Installing dependencies..."
    sudo apt-get update
    sudo apt install ffmpeg -y
    sudo apt-get install rabbitmq-server -y --fix-missing
    sudo systemctl start rabbitmq-server

    echo -e "\n[+] Installing pip dependencies"
    pip install pip --upgrade
    pip install -r requirements_torch.txt
    pip install -r requirements_demucs.txt
    pip install -r requirements_api.txt

    echo -e "\n[+] Starting rabbitmq server..."
    sudo rabbitmq-server start -detached & 
    sleep 2
fi

echo -e "\n[+] Starting API at 0.0.0.0:8000..."
python3 api.py

echo -e "\n[-] Cleaning all received and produced files"
sudo rm -r uploads
sudo rm -r download
