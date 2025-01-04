Fix path for nvcc (PATH, LD_LIBRARY_PATH)
Sim link for libcusprase

Install torch from nvidia source
Install libcusparseLt from nvidia source

Build CTranslate2 following pip page manual installation
After git clone:

```bash
mkdir build
cd build
cmake .. -DWITH_CUDA=ON -DWITH_CUDNN=ON -DWITH_MKL=OFF
make -j4
```

then followed python installation and added path to LD_LIBRARY_PATH

Becareful when installing anything torch - it auto-removes previous installation (namely torch-2.5.0)

# torchaudio
Build your own:
https://pytorch.org/audio/2.5.0/build.jetson.html


# CMAKE
if errors on CMAKE:
Errors:
```bash
    CMake Error: CMAKE_C_COMPILER not set, after EnableLanguage
    CMake Error: CMAKE_CXX_COMPILER not set, after EnableLanguage
```


Install:
```bash
sudo apt install build-essential
```

Check:
```bash
gcc --version
g++ --version
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

# torchaudio
Note I had to *lower power to 7w*!

```bash
git clone audio
...

sudo -E python3 setup.py install
```

Useful repo:
https://github.com/dusty-nv/jetson-containers
Problem: JetPack 5.1
