#!/bin/bash

# Set the repository local path
LOCAL_PATH="/home/ori.nachum/git/raspi"

# Change to the local repository path
cd "$LOCAL_PATH"

# Pull the latest changes from the remote repository
git pull

# You can add additional commands here if needed, such as installing dependencies or building your project