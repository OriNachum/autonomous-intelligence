#!/bin/bash

# Set the path to the Nmap binary
# NMAP_PATH="/usr/bin/nmap"
START_LOCATION="/home/ori.nachum/git/tau"

source  $START_LOCATION/.env


# Set the network range to scan
NETWORK_RANGE="192.168.1.0/24"

# Set the output file path and name
OUTPUT_FILE="./batch/output/nmap_output.txt"

# Run Nmap and save the output to the specified file
pwd
cd $START_LOCATION
pwd
output=`sudo nmap -sn "$NETWORK_RANGE" | grep $EXTENSION_VISION_MAC -B 2 | grep scan`
ip="${output##*for }"
echo $ip > $OUTPUT_FILE
