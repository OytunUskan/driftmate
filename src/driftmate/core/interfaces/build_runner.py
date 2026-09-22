from typing import Protocol

from driftmate.core.models.build import BuildResult, Status


class BuildRunner(Protocol):
    def build(
        self,
        sourceRef: str,
        imageTag: str,
        context_path: str | None = None,
    ) -> BuildResult: ...

    def push(self, imageTag: str, registryTarget: str) -> None: ...

    def getStatus(self, buildId: str) -> Status: ...
