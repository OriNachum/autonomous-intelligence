import torch
import torchaudio # No sounddevice
import torchaudio.transforms as T
import numpy as np
import wave
import io
import time
import logging
from queue import Queue
from threading import Thread
from faster_whisper import WhisperModel
import onnxruntime as ort

class SpeechTranscriber:
    def __init__(self, on_transcription=None, device='cuda', model_size="small", initial_prompt=None):
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
        self.device = torch.device(device)
        self.vad_model, _ = torch.hub.load('snakers4/silero-vad', 'silero_vad', force_reload=False)
        self.vad_model = self.vad_model.to(self.device)
        
        self.whisper_model = WhisperModel(model_size, device=device, compute_type="int8")
        
        self.rate = 16000
        self.chunk_duration = 0.032  # 32ms chunks
        self.chunk_samples = int(self.rate * self.chunk_duration)
        
        self.threshold = 0.5
        self.speaking = False
        self.silence_duration = 0
        self.max_silence_duration = 2.0
        
        self.audio_buffer = []
        self.is_recording = False
        self.initial_prompt = initial_prompt
        self.on_transcription = on_transcription

    def transcribe_audio(self, audio_data):
        try:
            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.rate)
                wf.writeframes(b''.join([chunk.numpy().tobytes() for chunk in audio_data]))
            
            wav_buffer.seek(0)
            segments, _ = self.whisper_model.transcribe(
                wav_buffer,
                beam_size=5,
                initial_prompt=self.initial_prompt,
                language='en',
                condition_on_previous_text=True
            )
            
            return " ".join(segment.text for segment in segments).strip()
        except Exception as e:
            self.logger.error(f"Transcription error: {str(e)}")
            return ""

    def process_audio(self, audio_chunk):
        try:
            audio_tensor = audio_chunk.to(self.device)
            speech_prob = self.vad_model(audio_tensor, self.rate).item()
            
            if speech_prob > self.threshold:
                if not self.speaking:
                    self.logger.info("Speech detected")
                    self.speaking = True
                    self.audio_buffer = []
                self.audio_buffer.append(audio_chunk)
                self.silence_duration = 0
            else:
                if self.speaking:
                    self.silence_duration += self.chunk_duration
                    self.audio_buffer.append(audio_chunk)
                    
                    if self.silence_duration > self.max_silence_duration:
                        self.logger.info("Processing speech segment")
                        self.speaking = False
                        self.silence_duration = 0
                        
                        if self.audio_buffer:
                            transcription = self.transcribe_audio(self.audio_buffer)
                            if transcription and self.on_transcription:
                                self.on_transcription(transcription)
                            self.audio_buffer = []

        except Exception as e:
            self.logger.error(f"Error processing audio: {str(e)}")

    def start(self):
        try:
            self.is_recording = True
            
            # Initialize audio capture
            audio_pipe = torchaudio.io.AudioIOStream(
                src=None,  # Use default input device
                format="default",
                channels=1,
                sample_rate=self.rate
            )
            
            resampler = T.Resample(
                orig_freq=audio_pipe.sample_rate,
                new_freq=self.rate
            )

            self.logger.info("Started recording. Speak to test...")
            
            with audio_pipe:
                buffer = torch.zeros(self.chunk_samples)
                while self.is_recording:
                    chunk = audio_pipe.read(self.chunk_samples)
                    if chunk is not None:
                        # Resample if necessary
                        if audio_pipe.sample_rate != self.rate:
                            chunk = resampler(chunk)
                        self.process_audio(chunk)
                    time.sleep(0.01)
                    
        except Exception as e:
            self.logger.error(f"Recording error: {str(e)}")
        finally:
            self.stop()

    def stop(self):
        self.is_recording = False
        self.logger.info("Recording stopped")

def main():
    def handle_transcription(text):
        print(f"\nTranscription: {text}")
    
    transcriber = SpeechTranscriber(
        on_transcription=handle_transcription,
        initial_prompt="The following is a transcription of speech:",
        model_size="small",
        device="cuda"
    )
    
    try:
        transcriber.start()
    except KeyboardInterrupt:
        transcriber.stop()

if __name__ == "__main__":
    main()