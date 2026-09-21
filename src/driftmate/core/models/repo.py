from dataclasses import dataclass


@dataclass
class Content:
    path: str
    content: str
    sha: str
    encoding: str = "plaintext"
    is_binary: bool = False
    truncated: bool = False


@dataclass
class Branch:
    name: str
    commit_sha: str
    ref: str


@dataclass
class RemoteRef:
    name: str
    url: str
