from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Status(Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


@dataclass
class BuildResult:
    build_id: str
    status: Status
    logs: Optional[str] = None
    image_tag: Optional[str] = None
