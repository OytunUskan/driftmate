"""GitHub implementation of the RepoProvider interface (via PyGithub)."""

import base64
import logging

from github import Github
from github.GithubException import GithubException, RateLimitExceededException

from driftmate.core.models.repo import Branch, Content, RemoteRef

logger = logging.getLogger(__name__)


class FileNotFoundError_(Exception):
    """Raised when a file or branch is not found in the repository."""


class GitHubRepoProvider:
    def __init__(self, token: str, owner: str, repo: str) -> None:
        self._client = Github(token)
        self._repo = self._client.get_repo(f"{owner}/{repo}")
        self.owner = owner
        self.repo_name = repo

    def getFile(self, path: str, ref: str) -> Content:
        try:
            contents = self._repo.get_contents(path, ref=ref)
        except RateLimitExceededException:
            logger.error("GitHub rate limit exceeded for getFile(%s, %s)", path, ref)
            raise
        except GithubException as exc:
            if exc.status == 404:
                raise FileNotFoundError_(f"{path} not found at ref {ref}") from exc
            raise

        if isinstance(contents, list):
            raise FileNotFoundError_(f"{path} is a directory, not a file")

        encoding = contents.encoding or "utf-8"
        if contents.content is None:
            return Content(
                path=path,
                content="",
                sha=contents.sha,
                encoding=encoding,
                is_binary=False,
                truncated=True,
            )

        if encoding == "base64":
            decoded = base64.b64decode(contents.content)
            try:
                raw = decoded.decode("utf-8")
                is_binary = False
            except UnicodeDecodeError:
                raw = decoded.decode("latin-1")
                is_binary = True
        else:
            raw = contents.content
            is_binary = False

        return Content(
            path=path,
            content=raw,
            sha=contents.sha,
            encoding=encoding,
            is_binary=is_binary,
            truncated=bool(getattr(contents, "truncated", False)),
        )

    def createBranch(self, name: str, fromRef: str) -> Branch:
        try:
            from_branch = self._repo.get_branch(fromRef)
        except GithubException as exc:
            if exc.status == 404:
                raise FileNotFoundError_(f"Branch {fromRef} not found") from exc
            raise

        commit_sha = from_branch.commit.sha
        ref = f"refs/heads/{name}"

        try:
            self._repo.create_git_ref(ref=ref, sha=commit_sha)
        except GithubException as exc:
            if exc.status == 422:
                existing = self._repo.get_branch(name)
                return Branch(name=name, commit_sha=existing.commit.sha, ref=ref)
            raise

        return Branch(name=name, commit_sha=commit_sha, ref=ref)

    def commitFile(self, branch: str, path: str, content: str, message: str) -> None:
        try:
            existing = self.getFile(path, branch)
        except FileNotFoundError_:
            existing = None

        if existing is not None:
            self._update_with_retry(branch, path, content, message)
        else:
            self._repo.create_file(
                path=path,
                message=message,
                content=content,
                branch=branch,
            )

    def _update_with_retry(
        self, branch: str, path: str, content: str, message: str
    ) -> None:
        for attempt in range(2):
            existing = self.getFile(path, branch)
            try:
                self._repo.update_file(
                    path=path,
                    message=message,
                    content=content,
                    sha=existing.sha,
                    branch=branch,
                )
                return
            except GithubException as exc:
                if exc.status == 409 and attempt == 0:
                    logger.warning(
                        "Concurrent edit on %s; retrying (attempt %d)", path, attempt + 1
                    )
                    continue
                raise

    def publishBranch(self, branch: Branch) -> RemoteRef:
        url = (
            f"https://github.com/{self.owner}/{self.repo_name}/tree/{branch.name}"
        )
        return RemoteRef(name=branch.name, url=url)
