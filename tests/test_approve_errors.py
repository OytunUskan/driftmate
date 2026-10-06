"""handle_approve must tell the user when a bump cannot be applied, without touching the repo."""

from unittest.mock import MagicMock

from driftmate.core.services.remediation_orchestrator import RemediationOrchestrator


def _orchestrator(file_content):
    repo = MagicMock()
    repo.getFile.return_value = MagicMock(content=file_content)
    notification = MagicMock()
    orch = RemediationOrchestrator(
        repo=repo,
        notification=notification,
        build_runner=MagicMock(),
        analyzer=MagicMock(),
    )
    return orch, repo, notification


def _sent_texts(notification):
    return " ".join(str(c.args[0]) for c in notification.sendMessage.call_args_list)


def test_unmatched_component_reports_and_does_not_commit():
    orch, repo, notification = _orchestrator("FROM python:3.11-slim\n")
    orch.handle_approve("u1", {"component": "nginx", "target_version": "1.27", "package_file": "Dockerfile"})

    repo.commitFile.assert_not_called()
    repo.publishBranch.assert_not_called()
    repo.createBranch.assert_not_called()
    text = _sent_texts(notification)
    assert "nginx" in text
    assert "Dockerfile" in text


def test_matching_component_still_commits():
    orch, repo, notification = _orchestrator("FROM nginx:1.25\n")
    repo.createBranch.return_value = MagicMock(name="branch")
    repo.publishBranch.return_value = MagicMock(url="https://example/x")
    orch.handle_approve("u1", {"component": "nginx", "target_version": "1.27", "package_file": "Dockerfile"})

    repo.commitFile.assert_called_once()
    assert "FROM nginx:1.27" in repo.commitFile.call_args[0][2]
