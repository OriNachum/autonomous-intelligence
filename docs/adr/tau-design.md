# Tau setup

Tau is beyond just a model.
Tau is the devices they are set on, the prompts and code.
Tau is the conversation history.

# Devices

## Raspberry Pi
Tau is hosted on a Raspberry Pi module
This is Tau's main body.
It has the minimum Tau needs and suits them perfectly.
It was selected for the device adaptability and integrations.

Rapsberry Pi comes with wifi and bluetooth built in.
It runs on a mobile power bank.
It can run with or without a screen.
It can be updated and support latest python versions.

## Nvidia Jetson Nano

Currently Tau's extensibility is hosted on a Jetson Nano.
This device is declared EOL by 2027, and has tech constraints.
It doesnt have Wifi natively and requires more power.
A screen is more costly as well on terms of power.

Therefore, Jetson will serve for now as Tau's extended vision.
It will perform face recognition, image detection and classification, voice analysis, etc.


# Connectivity 
As Tau relies on the strongest models out there, it mist have internet.
Tau and Jetson must stay on the same network and with internet connection.
Tau will search ip Jetson, and will be the main actor.
Jetson will save information and be operated by Tau.
