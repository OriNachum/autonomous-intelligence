# General 

Main app “Tau” on Raspberry  Pi connects to “Vision” on a Nvidia Jetson device including Facial recognition.  
Tau is also connected to “speech” on current device by using OpenAI speech to text and a “Tau Speech” app, and to “Face app” “Tau speech” also connected to the “Face app”.  
“Tau” also connected to hearing, and memory features.

## Visual
```mermaid
graph TD
  Tau[Tau App] -->|connects to| Vision[Vision on Nvidia Jetson]
  Vision -->|includes| FR[Facial Recognition]
  
  Tau -->|connects to| Speech[Speech on Raspberry Pi]
  Speech -->|uses| OpenAI[OpenAI Speech to Text]

  Tau -->|connects to| TauSpeech[Tau Speech App]
  TauSpeech -->|connected to| FaceApp[Face App]

  Tau -->|connects to| Hearing[Hearing Feature]
  Tau -->|connects to| Memory[Memory Feature]
```