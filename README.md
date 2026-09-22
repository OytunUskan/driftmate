# Driftmate

Detect Kubernetes/Helm component version drift and propose human-approved
remediation via a ChatOps "analyze + fix" flow.

Driftmate compares component versions declared in a target repository against
the versions declared in their upstream GitHub repositories (Option A). There
is no live cluster connection.

## Architecture

Driftmate is vendor-agnostic and built around three interfaces plus an
independent core:

- `RepoProvider` — `getFile` / `createBranch` / `commitFile` / `publishBranch`
- `NotificationChannel` — `sendMessage` / `updateMessage` / `onAction`
- `BuildRunner` — `build` / `push` / `getStatus`

Dependency direction is inward only: adapters (`providers/`, `channels/`,
`build/`) import `core/`, but `core/` never imports any adapter module.
The package lives under `src/driftmate/`.

V1 scope:

- RepoProvider: GitHub (PyGithub)
- NotificationChannel: Telegram long-polling (python-telegram-bot)
- BuildRunner: local Docker (Docker SDK for Python)

## Quick start

1. Install globally with low friction via pipx (or `pip install -e .` for development):
   ```bash
   pipx install .
   ```
2. Run the guided interactive setup to configure your tokens and test Docker daemon health:
   ```bash
   driftmate init
   ```
   *(This guides you through setting up `GITHUB_TOKEN`, `TELEGRAM_BOT_TOKEN`, and automatically detects your `TELEGRAM_CHAT_ID` by prompting you to send a message to your bot).*
3. Run Driftmate:
   ```bash
   driftmate
   ```

## Configuration

`config.yaml` selects the active adapters. Credentials are never stored as
values; each `*_env` field is an environment variable name resolved at load
time. See `.env.example` for the required variables.

Required env vars: `GITHUB_TOKEN`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
Registry vars (`DOCKER_REGISTRY_URL`, `DOCKER_USERNAME`, `DOCKER_PASSWORD`)
are **optional** — v1 does local builds only and never pushes to a registry.

## Component Discovery (Renovate)

Driftmate no longer requires a `driftmate.yaml` file. Instead, it utilizes the [Renovate CLI](https://docs.renovatebot.com/) to automatically discover dependencies in your repository.

- **Supported Formats**: Dockerfiles, Helm Charts, Terraform modules, and more.
- **How it works**: When you run `driftmate` (analyze), it automatically scans your project for standard manifest files and compares them against upstream registries.
- **Remediation**: When you approve a version bump in Telegram, Driftmate automatically applies the fix directly to the native configuration file (e.g., `Dockerfile`, `Chart.yaml`).


## Local build (worktree)

On approval, the fix is committed to a branch and (optionally) built locally.
Set `checkout_path` in `config.yaml` to a local clone of the target repo; the
orchestrator then runs `git worktree add` for the fix branch, builds from that
temporary path, and removes the worktree afterwards. Without `checkout_path`
the build step is skipped.

## State management (known limitation)

Telegram short-ID -> drift-context mapping is stored in an in-memory store
(`channels/common/state_store.py`). **It is lost when the bot restarts.** This
is a deliberate V1 limitation; a persistent store (Redis/SQLite) is planned.

## Development

```bash
pip install -e ".[test]"
pytest
mypy src/driftmate
```

Core isolation check:

```bash
grep -rnE "from (providers|channels|build)|import (providers|channels|build)" src/driftmate/core/ && echo VIOLATION || echo OK
```

## Backlog (V2+)

- Persistent state store (Redis/SQLite)
- The `push()` adapter is implemented but not wired in the V1 remediation flow; builds only produce local images, and registry pushes are not performed (conscious V1 limitation).
- **Azure DevOps RepoProvider (V2 feasibility):** Azure DevOps REST API — `getFile` via `GET /{project}/_apis/git/repositories/{repositoryId}/items?path=...`. The **`createBranch`, `commitFile`, and `publishBranch`** methods cannot be called separately as in GitHub; in Azure DevOps, all are performed via a **single pushes endpoint**: `POST /{project}/_apis/git/repositories/{repositoryId}/pushes` (apiVersion 7.0+). The request body includes `refUpdates` (branch name + old commit SHA) and `commits[].changes[]` (file path, changeType: `add`/`edit`/`delete`, content). PAT scope: `Code (Read/Write)` (`vso.code_write`). The ADO adapter must combine the three separate methods of the Protocol interface into this single push call.
- **Slack NotificationChannel (V2 feasibility):** `sendMessage` → `chat.postMessage`; `updateMessage` → `chat.update`; `onAction` → **Socket Mode** for interactive button feedback (no public HTTPS endpoint / ngrok required, works from WSL2 — same model as Telegram polling). Slack Socket Mode is WebSocket-based; whereas Telegram uses long-polling + `update.callback_query`, Slack uses `SocketModeHandler` to listen for `interactivity` events.
- AI risk report, Slack, Azure DevOps, AWS CodeBuild
- Kubernetes manifest drift analysis
- Webhook-based notification instead of long-polling
- CI/CD integration (auto-trigger on branch merge)
- Docker containerization (requires mounting `docker.sock` and a volume for `git worktree` paths if running inside a container).
