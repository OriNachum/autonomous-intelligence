# Baby Tau

This is a demo project of whisper-ollama-piperTTS  
It can all run on Raspberry pi (Slow) or Nvidia Jetson Orin Nano Super (fast)   
Its purpose is testing libraries on Jetson and POCing the setup.

## piper-tts
### Example use
```bash
echo 'Welcome to the world of speech synthesis!' | piper   --model en_US-lessac-medium   --output_file welcome.wav
```

### Troubleshoot

```bash
/home/tau/git/autonomous-intelligence/baby-tau/.venv/lib/python3.10/site-packages/onnxruntime/capi/onnxruntime_inference_collection.py:115: UserWarning: Specified provider 'CUDAExecutionProvider' is not in available provider names.Available providers: 'AzureExecutionProvider, CPUExecutionProvider'
```
Remove onnx and install from wheel
```bash
pip uninstall onnxrunttime
wget ..
pip install ... 
```

Other error
```bash
`ONNX Available providers: ['TensorrtExecutionProvider', 'CUDAExecutionProvider', 'CPUExecutionProvider']
Unsupported ONNX data type: <UNKNOWN> (0)
Unsupported ONNX data type: <UNKNOWN> (0)
Unsupported ONNX data type: <UNKNOWN> (0)
2025-01-11 09:28:58.070972436 [E:onnxruntime:, inference_session.cc:2117 operator()] Exception during initialization: /opt/onnxruntime/onnxruntime/core/providers/tensorrt/tensorrt_execution_provider.cc:2220 SubGraphCollection_t onnxruntime::TensorrtExecutionProvider::GetSupportedList(SubGraphCollection_t, int, int, const onnxruntime::GraphViewer&, bool*) const [ONNXRuntimeError] : 1 : FAIL : TensorRT input: /SplitToSequence_output_0 has no shape specified. Please run shape inference on the onnx model first. Details can be found in https://onnxruntime.ai/docs/execution-providers/TensorRT-ExecutionProvider.html#shape-inference-for-tensorrt-subgraphs

2025-01-11 09:28:58,094 - ERROR - Error in process_audio: [ONNXRuntimeError] : 6 : RUNTIME_EXCEPTION : Exception during initialization: /opt/onnxruntime/onnxruntime/core/providers/tensorrt/tensorrt_execution_provider.cc:2220 SubGraphCollection_t onnxruntime::TensorrtExecutionProvider::GetSupportedList(SubGraphCollection_t, int, int, const onnxruntime::GraphViewer&, bool*) const [ONNXRuntimeError] : 1 : FAIL : TensorRT input: /SplitToSequence_output_0 has no shape specified. Please run shape inference on the onnx model first. Details can be found in https://onnxruntime.ai/docs/execution-providers/TensorRT-ExecutionProvider.html#shape-inference-for-tensorrt-subgraphs

2025-01-11 09:28:59,808 - INFO - Recording stopped and resources cleaned up
```

# Check specs
```bash
sudo pip3 install -U jetson-stats 
sudo reboot
```



# New instructions
## Initialize and update the submodule
git submodule update --init --recursive

