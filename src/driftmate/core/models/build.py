from dataclasses import dataclass
from enum import Enum


class Status(Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


@dataclass
class BuildResult:
    build_id: str
    status: Status
    logs: str | None = None
    image_tag: str | None = None
