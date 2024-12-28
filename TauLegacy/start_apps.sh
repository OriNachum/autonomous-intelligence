#!/bin/bash

# Navigate to hailo-example and run
cd ~/git/hailo-example
source setup_env.sh
./run_service.sh &
echo "hailo-example started"

# Navigate to autonomous-intelligence and run face_service.py
cd ~/git/autonomous-intelligence
source init_env.sh
python services/face_service.py &
echo "face_service.py started"

# Run tau.py
source init_env.sh
python tau.py &
echo "tau.py started"

# Run tau_speech.py
source init_env.sh
python tau_speech.py &
echo "tau_speech.py started"

# Run microphone_listener.py
source init_env.sh
python services/microphone_listener.py &
echo "microphone_listener.py started"

wait