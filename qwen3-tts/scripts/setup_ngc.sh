#!/usr/bin/env bash
# Setup NGC API key for pulling NVIDIA NIM containers
set -euo pipefail

read -rsp "Paste your NGC API key (nvapi-...): " NGC_API_KEY
echo

# Login to NGC Docker registry
echo "$NGC_API_KEY" | docker login nvcr.io --username '$oauthtoken' --password-stdin

# Save to bashrc
if ! grep -q NGC_API_KEY ~/.bashrc 2>/dev/null; then
  echo "export NGC_API_KEY=\"$NGC_API_KEY\"" >> ~/.bashrc
fi

echo "Done! NGC key saved and Docker logged into nvcr.io"
