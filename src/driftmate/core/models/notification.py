from dataclasses import dataclass
from typing import Optional


@dataclass
class Action:
    id: str
    label: str
    metadata: Optional[dict] = None


@dataclass
class MessageRef:
    message_id: int
    chat_id: str
