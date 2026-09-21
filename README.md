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

1. Clone the repository (inside WSL filesystem, never `/mnt/c/...`).
2. Copy `.env.example` to `.env` and fill in the tokens. `.env` is loaded
   automatically at startup via `python-dotenv`.
3. Install: `pip install -e .`
4. Verify the Docker daemon: `docker ps`
5. Run: `driftmate` (or `python -m driftmate.app.main`)

## Configuration

`config.yaml` selects the active adapters. Credentials are never stored as
values; each `*_env` field is an environment variable name resolved at load
time. See `.env.example` for the required variables.

Required env vars: `GITHUB_TOKEN`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
Registry vars (`DOCKER_REGISTRY_URL`, `DOCKER_USERNAME`, `DOCKER_PASSWORD`)
are **optional** — v1 does local builds only and never pushes to a registry.

## Manifest

The target repository declares its components in `driftmate.yaml`:

```yaml
components:
  - name: ingress-nginx
    version: "1.9.5"
    upstream:
      owner: kubernetes
      repo: ingress-nginx
      path: charts/ingress-nginx/Chart.yaml
      ref: main
      version_key: version
```

- `version_key` is optional; when omitted the upstream file is read as plain text.
- Versions **must be quoted strings**. Unquoted versions (e.g. `1.10`) are
  coerced to numbers by YAML and cause a `ValueError` at parse time to avoid
  silent data loss.

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
- Registry push (docker push) wiring
- AI risk report, Slack, Azure DevOps, AWS CodeBuild
- Kubernetes manifest drift analysis
- Webhook-based notification instead of long-polling
- CI/CD integration (auto-trigger on branch merge)
