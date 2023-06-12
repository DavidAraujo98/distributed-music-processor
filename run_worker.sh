#!/bin/bash

# ./run_worker.sh 1 [127.0.0.1]

echo -e "[-] Cleaning all received and produced files"
sudo rm -r *_received &>/dev/null
sudo rm -r *_processed &>/dev/null

echo "[+] Creating environment..."
python3 -m venv venv    &>/dev/null
source venv/bin/activate    &>/dev/null

for i in $(seq 1 $1); do
    echo "[+] Starting worker..."
    SERVER=""
    if [[ $2 != "" ]]; then
        SERVER="-server ${2}"
    fi
    python3 worker.py ${SERVER} & &>/dev/null
    echo -e "[+] Worker with PID $! started..."
done