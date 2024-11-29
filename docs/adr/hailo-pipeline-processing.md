# Hailo processing decisions

## Location

Hailo works in a pipeline running inference on the Raspberry Pi camera feed, provided video or provided image.  
Setup requires starting with their specific script, then running their pipeline.  

Since Tau is an already existing project, integration around their pipeline is complex.  
Additionally, I'd prefer to avoid vendor lock - especially if they change the way they work.

Therefore, the pipeline will remain on a fork of their repo, to keep getting updates and also seperate applications.

## Communication

Communication will be event-based, and since it is the same device - Unix Domain Events.

## Processing

Hailo pipeline can support multiple models.  
For Tau, I need to process 5 models on the same camera feed:
- Object detection
- Face recognition
- Pose detection
- Scene understanding
- Text extraction

The processing is recommended to run as close to the pipeline, so the implementation will happen on Hailo pipeline, and only relevant events will be shared with with the model.

## Inconsistencies

For inconsistent detections, a system of "object uptime" will be implemented.  
Each object detection will be kept in a rolling log.
On each change, "currently viewable" objects will be sent based on a threshold of average uptime: an object detected 60% or more of the time will start to be considered visible.
On move to below 30% current status of percentage of "uptime" - an event will be fired on object no long visible.  

This gives a leeway - 60% and the object begins to appear, have a major drop, and it's not longer visible.  
Percentages may change after testing.
