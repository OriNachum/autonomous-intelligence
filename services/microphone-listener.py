import socket
import pyaudio
import soundfile as sf
import numpy as np
import time 
#import librosa
from scipy.signal import find_peaks


# Unix domain socket setup
#sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
#server_address = '/tmp/sound_events'
#sock.bind(server_address)
#sock.listen(1)
#connection, _ = sock.accept()

print("started")

# Audio setup
p = pyaudio.PyAudio()
stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=1024)

# Initialize variables to track volume state
prev_state = False  # False means volume is not high initially
stop_time = None
start_time = None
# Open WAV file in append mode
with sf.SoundFile('temp_audio.wav', mode='w', samplerate=16000, channels=1) as f:
    while True:
        # Read audio data
        data = np.frombuffer(stream.read(1024, exception_on_overflow=False), dtype=np.int16)

        # Write audio data to the file
        f.write(data)
        
        # Calculate audio level
        level = np.max(np.abs(data))
        
       
        # Analyze audio for pitch and frequencies
        #y, sr = librosa.load(data, sr=16000)  # Load the audio data directly from the buffer
        #pitches, magnitudes = librosa.piptrack(y=y, sr=sr)  # Extract pitch information
        #frequencies = pitches[np.nonzero(pitches)]  # Extract frequencies from pitch information

        # Check if volume is high enough to emit an event
        if level > 10000:
            # Calculate autocorrelation for pitch detection
            autocorr = np.correlate(data, data, mode='full')
            autocorr = autocorr[len(autocorr)//2:]  # Keep only positive lags
        
            # Find peaks in autocorrelation to detect pitch
            peaks, _ = find_peaks(autocorr, height=10000)  # Adjust height threshold as needed
        
            if len(peaks) > 0:
                # Calculate pitch in Hz
                pitch_hz = 16000 / peaks[0]
                print("Pitch:", pitch_hz)

            #print("Pitch:", np.mean(frequencies))  # Print average pitch
            #print("Frequencies:", frequencies)    # Print frequencies
            if not prev_state:  # If volume was not high previously
                start_time = time.time()
                print(f"Volume became high: {start_time} ({0 if stop_time is None else start_time - stop_time})")
                prev_state = True  # Update state to indicate volume is now high
                
        else:
            if prev_state:  # If volume was high previously
                stop_time = time.time()
                print(f"Volume no longer high: {stop_time} ({stop_time-start_time})")
                prev_state = False  # Update state to indicate volume is no longer high

# Cleanup
stream.stop_stream()
stream.close()
p.terminate()
