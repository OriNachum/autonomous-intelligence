import pyaudio

def list_audio_devices():
    p = pyaudio.PyAudio()
    info = p.get_host_api_info_by_index(0)
    num_devices = info.get('deviceCount')
    
    print("Available audio devices:")
    for i in range(num_devices):
        device_info = p.get_device_info_by_host_api_device_index(0, i)
        device_name = device_info.get('name')
        max_input_channels = device_info.get('maxInputChannels')
        if max_input_channels > 0:
            print(f"Index {i}: {device_name} (Input)")
        else:
            print(f"Index {i}: {device_name} (Output)")
    
    p.terminate()

if __name__ == "__main__":
    list_audio_devices()
