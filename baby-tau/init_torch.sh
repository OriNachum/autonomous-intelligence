#!/bin/bash

wget_if_not_exists() {
    local url="$1"
    local filename="$2"
    
    # If filename is not provided, extract it from the URL
    if [ -z "$filename" ]; then
        filename=$(basename "$url")
    fi
    
    if [ ! -f "$filename" ]; then
        echo "File $filename does not exist. Downloading..."
        wget "$url" -O "$filename"
        
        # Check if download was successful
        if [ $? -eq 0 ]; then
            echo "Successfully downloaded $filename"
            return 0
        else
            echo "Failed to download $filename"
            return 1
        fi
    else
        echo "File $filename already exists. Skipping download."
        return 0
    fi
}

wget_if_not_exists https://developer.download.nvidia.com/compute/cusparselt/0.6.3/local_installers/cusparselt-local-tegra-repo-ubuntu2204-0.6.3_1.0-1_arm64.deb
sudo dpkg -i cusparselt-local-tegra-repo-ubuntu2204-0.6.3_1.0-1_arm64.deb
sudo cp /var/cusparselt-local-tegra-repo-ubuntu2204-0.6.3/cusparselt-*-keyring.gpg /usr/share/keyrings/
sudo apt-get update
sudo apt-get -y install libcusparselt0 libcusparselt-dev

wget_if_not_exists https://developer.download.nvidia.com/compute/redist/jp/v61/pytorch/torch-2.5.0a0+872d972e41.nv24.08.17622132-cp310-cp310-linux_aarch64.whl
pip install torch-2.5.0a0+872d972e41.nv24.08.17622132-cp310-cp310-linux_aarch64.whl 

echo " ========================================================"
echo " Installing from https://pypi.jetson-ai-lab.dev/jp6/cu126" 
echo " ========================================================"
echo ""

# Add grep pip list | ctranslate2
echo " Installing ctranslate2 from https://pypi.jetson-ai-lab.dev/jp6/cu126" 
wget_if_not_exists  https://pypi.jetson-ai-lab.dev/jp6/cu126/+f/6d2/9d09ec4904d72/ctranslate2-4.5.0-cp310-cp310-linux_aarch64.whl
pip install ctranslate2-4.5.0-cp310-cp310-linux_aarch64.whl 

# Add grep pip list | torchaudio
echo ""
echo " Installing torchaudio from https://pypi.jetson-ai-lab.dev/jp6/cu126" 
wget_if_not_exists https://pypi.jetson-ai-lab.dev/jp6/cu126/+f/812/4fbc4ba6df0a3/torchaudio-2.5.0-cp310-cp310-linux_aarch64.whl#sha256=8124fbc4ba6df0a30b1d8176aa5ce6f571c2dd5263e6401109d2e29708352c97
pip install torchaudio-2.5.0-cp310-cp310-linux_aarch64.whl

wget_if_not_exists https://pypi.jetson-ai-lab.dev/jp6/cu126/+f/0c4/18beb3326027d/onnxruntime_gpu-1.20.0-cp310-cp310-linux_aarch64.whl#sha256=0c418beb3326027d83acc283372ae42ebe9df12f71c3a8c2e9743a4e323443a

# For getting pth models
curl -s https://packagecloud.io/install/repositories/github/git-lfs/script.deb.sh | sudo bash
sudo apt-get install git-lfs
