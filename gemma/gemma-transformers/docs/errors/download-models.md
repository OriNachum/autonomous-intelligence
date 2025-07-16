emma3n-api-1  | Model cache directory: /cache/huggingface
gemma3n-api-1  | 
gemma3n-api-1  | Checking for cached model...
gemma3n-api-1  | No model files found in cache
gemma3n-api-1  | Model not found in cache, downloading...
gemma3n-api-1  | This may take 10-30 minutes on first run...
gemma3n-api-1  | 
gemma3n-api-1  | /usr/local/lib/python3.10/dist-packages/transformers/utils/hub.py:127: FutureWarning: Using `TRANSFORMERS_CACHE` is deprecated and will be removed in v5 of Transformers. Use `HF_HOME` instead.
gemma3n-api-1  |   warnings.warn(
gemma3n-api-1  | /usr/local/lib/python3.10/dist-packages/torchvision/io/image.py:13: UserWarning: Failed to load image Python extension: '/usr/local/lib/python3.10/dist-packages/torchvision/image.so: undefined symbol: _ZN5torch3jit17parseSchemaOrNameERKSs'If you don't plan on using image functionality from `torchvision.io`, you can ignore this warning. Otherwise, there might be something wrong with your environment. Did you have `libjpeg` or `libpng` installed before building `torchvision` from source?
gemma3n-api-1  |   warn(
gemma3n-api-1  | Traceback (most recent call last):
gemma3n-api-1  |   File "/app/download_model.py", line 10, in <module>
gemma3n-api-1  |     from transformers import AutoProcessor, Gemma3nForConditionalGeneration
gemma3n-api-1  | ImportError: cannot import name 'Gemma3nForConditionalGeneration' from 'transformers' (/usr/local/lib/python3.10/dist-packages/transformers/__init__.py)
gemma3n-api-1 exited with code 1