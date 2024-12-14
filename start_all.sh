#!/bin/bash

# Can be copied anywhere for convenience

# Expects Hailo repo
lxterminal -e "bash -c '~/git/autonomous-intelligence/run_scripts/run_vision.sh; exec bash'" &
lxterminal -e "bash -c '~/git/autonomous-intelligence/run_scripts/run_face.sh; exec bash'" &
lxterminal -e "bash -c '~/git/autonomous-intelligence/run_scripts/run_tau.sh; exec bash'" &
lxterminal -e "bash -c '~/git/autonomous-intelligence/run_scripts/run_speech.sh; exec bash'" &
lxterminal -e "bash -c '~/git/autonomous-intelligence/run_scripts/run_hearing.sh; exec bash'" &



#1. Open the autostart file:
#   nano ~/.config/lxsession/LXDE-pi/autostart
#2. Add the line to start your script:
#   @/home/pi/start_tau.sh
