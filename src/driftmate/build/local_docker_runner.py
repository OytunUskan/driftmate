"""Local Docker implementation of the BuildRunner interface."""

import logging

import docker

from driftmate.core.models.build import BuildResult, Status

logger = logging.getLogger(__name__)


class LocalDockerBuildRunner:
    def __init__(
        self,
        registry=None,
        dockerfile: str = "Dockerfile",
        build_context: str = ".",
    ) -> None:
        self._client = docker.from_env()
        self._registry = registry
        self._dockerfile = dockerfile
        self._build_context = build_context
        try:
            self._client.ping()
        except docker.errors.DockerException as exc:
            raise RuntimeError(
                "Docker daemon is not reachable. Is `docker ps` working?"
            ) from exc

    def build(
        self,
        sourceRef: str,
        imageTag: str,
        context_path: str | None = None,
    ) -> BuildResult:
        if context_path is None:
            raise RuntimeError(
                "context_path is required; building from default context "
                "is not supported for fix branches"
            )
        try:
            self._client.images.build(
                path=context_path,
                dockerfile=self._dockerfile,
                tag=imageTag,
            )
        except docker.errors.DockerException as exc:
            logger.error("Docker build failed: %s", exc)
            return BuildResult(
                build_id=imageTag,
                status=Status.FAILED,
                logs=str(exc),
                image_tag=imageTag,
            )
        return BuildResult(
            build_id=imageTag,
            status=Status.SUCCEEDED,
            image_tag=imageTag,
        )

    def push(self, imageTag: str, registryTarget: str) -> None:
        if self._registry and self._registry.username:
            self._client.login(
                username=self._registry.username,
                password=self._registry.password,
                registry=registryTarget,
            )
        self._client.images.push(imageTag)

    def getStatus(self, buildId: str) -> Status:
        """Local builds are synchronous and identified by their image tag."""
        try:
            self._client.images.get(buildId)
            return Status.SUCCEEDED
        except docker.errors.ImageNotFound:
            return Status.FAILED
