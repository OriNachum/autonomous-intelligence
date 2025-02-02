
import json
import logging

class Message:
    def __init__(self, msg_type, sender, destination, payload, priority=0):
        self.msg_type = msg_type
        self.sender = sender
        self.destination = destination
        self.payload = payload
        self.priority = priority

    def to_json(self):
        return json.dumps(self.__dict__)

    @staticmethod
    def from_json(data):
        try:
            dict_obj = json.loads(data)
            return Message(
                dict_obj.get('msg_type'),
                dict_obj.get('sender'),
                dict_obj.get('destination'),
                dict_obj.get('payload'),
                dict_obj.get('priority', 0)
            )
        except Exception as e:
            logging.error(f"Failed to parse message: {e}")
            return None