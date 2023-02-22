from datetime import datetime


class Entity:
    def __init__(self, entity_type, value, context, file_id):
        self.entity_type = entity_type
        self.value = value
        self.context = context
        self.file_id = file_id

    def make_document(self):
        document = {
            "entity_type": self.entity_type,
            "value": self.value,
            "context": self.context,
            "file_id": self.file_id,
            "timestamp": datetime.now()
        }

        return document
