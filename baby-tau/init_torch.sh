#!/bin/bash


wget https://developer.download.nvidia.com/compute/cusparselt/0.6.3/local_installers/cusparselt-local-tegra-repo-ubuntu2204-0.6.3_1.0-1_arm64.deb
sudo dpkg -i cusparselt-local-tegra-repo-ubuntu2204-0.6.3_1.0-1_arm64.deb
sudo cp /var/cusparselt-local-tegra-repo-ubuntu2204-0.6.3/cusparselt-*-keyring.gpg /usr/share/keyrings/
sudo apt-get update
sudo apt-get -y install libcusparselt0 libcusparselt-dev

wget https://developer.download.nvidia.com/compute/redist/jp/v61/pytorch/torch-2.5.0a0+872d972e41.nv24.08.17622132-cp310-cp310-linux_aarch64.whl
pip install torch-2.5.0a0+872d972e41.nv24.08.17622132-cp310-cp310-linux_aarch64.whl 

echo " ========================================================"
echo " Installing from https://pypi.jetson-ai-lab.dev/jp6/cu126" 
echo " ========================================================"
echo ""

# Add grep pip list | ctranslate2
echo " Installing ctranslate2 from https://pypi.jetson-ai-lab.dev/jp6/cu126" 
wget https://pypi.jetson-ai-lab.dev/jp6/cu126/+f/6d2/9d09ec4904d72/ctranslate2-4.4.0-cp310-cp310-linux_aarch64.whl#sha256=6d29d09ec4904d721aa3e65fe6d52177e6644b55f64524cb72fe6867e8727bf7
pip install ctranslate2-4.4.0-cp310-cp310-linux_aarch64.whl 

# Add grep pip list | torchaudio
echo ""
echo " Installing torchaudio from https://pypi.jetson-ai-lab.dev/jp6/cu126" 
wget https://pypi.jetson-ai-lab.dev/jp6/cu126/+f/812/4fbc4ba6df0a3/torchaudio-2.5.0-cp310-cp310-linux_aarch64.whl#sha256=8124fbc4ba6df0a30b1d8176aa5ce6f571c2dd5263e6401109d2e29708352c97
pip install torchaudio-2.5.0-cp310-cp310-linux_aarch64.whl
