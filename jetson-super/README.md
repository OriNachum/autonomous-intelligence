Fix path for nvcc (PATH, LD_LIBRARY_PATH)
Sim link for libcusprase

Must download and install libcusparseLt.so first!
https://docs.nvidia.com/deeplearning/frameworks/install-pytorch-jetson-platform/index.html

```bash
wget https://developer.download.nvidia.com/compute/cusparselt/0.6.3/local_installers/cusparselt-local-tegra-repo-ubuntu2204-0.6.3_1.0-1_arm64.deb
sudo dpkg -i cusparselt-local-tegra-repo-ubuntu2204-0.6.3_1.0-1_arm64.deb
sudo cp /var/cusparselt-local-tegra-repo-ubuntu2204-0.6.3/cusparselt-*-keyring.gpg /usr/share/keyrings/
sudo apt-get update
sudo apt-get -y install libcusparselt0 libcusparselt-dev
```

Then you can install torch from source:
```bash
wget https://developer.download.nvidia.com/compute/redist/jp/v61/pytorch/torch-2.5.0a0+872d972e41.nv24.08.17622132-cp310-cp310-linux_aarch64.whl
pip3 install torch-2.5.0a0+872d972e41.nv24.08.17622132-cp310-cp310-linux_aarch64.whl 
```
verify torch with:
```python
import torch
print(f"Is CUDA installed: {torch.cuda.is_available()}")
print(f"CUDA version: {torch.version.cuda}")

```
Expect: 
```
Is CUDA installed: True
CUDA version: 12.6
```

If you installed torch first - reinstall with `--force-install`


## CTranslate2
No need to build from scratch, you have prebuilt: https://pypi.jetson-ai-lab.dev/jp6/cu126


### The hard way
Build CTranslate2 following pip page manual installation
https://pypi.org/project/ctranslate2/1.20.1/

**Compile and install**

```bash
cd ~/git
git clone https://github.com/OpenNMT/CTranslate2
cd CTranslate2
git submodule update --init --recursive
git submodule status
mkdir build && cd build
cmake -DWITH_CUDA=ON -DWITH_CUDNN=ON -DWITH_MKL=OFF ..
make -j4

# Install the CTranslate2 library.
cd build && make install && cd ..

# Build and install the Python wheel.
cd python
pip install -r install_requirements.txt
# This is optional, in case headers can't be found
export CPLUS_INCLUDE_PATH=~/git/CTranslate2/include:$CPLUS_INCLUDE_PATH 
python setup.py bdist_wheel
pip install dist/*.whl

```


then  add path to LD_LIBRARY_PATH


### Troubleshoot
Verify used --recrusive - or getting wrong version!
Below fixes partial errors, but new ones down the line with CUB

```bash
CMake Error at CMakeLists.txt:297 (message):
  Intel OpenMP runtime libiomp5 not found
```
Update the ../CMakeLists.txt on git root level:
```
set(OPENMP_RUNTIME "INTEL" CACHE STRING "OpenMP runtime (INTEL, COMP, NONE)")
```
Set "INTEL" to "COMP" 



## torchaudio
No need to build from scratch, you have prebuilt: https://pypi.jetson-ai-lab.dev/jp6/cu126

### the hard way
Becareful when installing anything torch - it auto-removes previous installation (namely torch-2.5.0)
Build your own:
Note I had to ***lower power to 7w***!
https://pytorch.org/audio/2.5.0/build.jetson.html


#### CMAKE
if errors on CMAKE:
Errors:
```bash
    CMake Error: CMAKE_C_COMPILER not set, after EnableLanguage
    CMake Error: CMAKE_CXX_COMPILER not set, after EnableLanguage
```


Install:
```bash
sudo apt install build-essential #No need
```

Check:
```bash
gcc --version #Already updated
g++ --version #Already updated 
```

Libary libnvToolsExt.so.1
```bash
sudo apt-get install nvidia-jetpack
```

Problem:
    CMake Error: CMake was unable to find a build program corresponding to "Ninja".  CMAKE_MAKE_PROGRAM is not set.  You probably need to select a different build tool.
    CMake Error: CMAKE_C_COMPILER not set, after EnableLanguage
    CMake Error: CMAKE_CXX_COMPILER not set, after EnableLanguage
    -- Configuring incomplete, errors occurred!

Fixed by:
```bash
sudo apt update
sudo apt install -y ninja-build gcc g++ cmake
```

Note I had to ***lower power to 7w***!

```bash
git clone https://github.com/pytorch/audio
...

sudo -E python3 setup.py install
```

Useful repo:
https://github.com/dusty-nv/jetson-containers
Problem: JetPack 5.1
