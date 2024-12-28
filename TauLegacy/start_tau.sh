#!/bin/bash

watch -n 30 sudo nmap -O 192.168.1.* > network_status.log
# command > /dev/null 2>&1 &

echo source .venv/bin/active
echo python tau.py
