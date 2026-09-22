from dataclasses import dataclass


@dataclass
class Action:
    id: str
    label: str
    metadata: dict | None = None


@dataclass
class MessageRef:
    message_id: int
    chat_id: str
