# Driftmate

## What is Driftmate

Driftmate is an open-source CLI for engineering teams that need to know
whether their dependency declarations (Helm charts, Terraform modules,
Dockerfiles) have drifted from upstream releases — without connecting to a
live cluster. It produces a structured `driftmate-report.md`, supports
standalone scanning (no tokens needed), and can escalate to an approved,
human-in-the-loop remediation flow through GitHub and Telegram.

## Architecture

Driftmate is built around three interfaces plus an independent core, so
each integration point can be swapped without touching core logic:

- `RepoProvider` — `getFile` / `createBranch` / `commitFile` / `publishBranch`
- `NotificationChannel` — `sendMessage` / `updateMessage` / `onAction`
- `BuildRunner` — `build` / `push` / `getStatus`

**Currently implemented:** GitHub (`RepoProvider`, via PyGithub), Telegram
(`NotificationChannel`, long-polling), and local Docker (`BuildRunner`). The
interfaces are vendor-agnostic by design — see `BACKLOG.md` for other
integrations under consideration (Azure DevOps, Slack) — but only the three
above ship today.

Dependency direction is inward only: adapters (`providers/`, `channels/`,
`build/`) import `core/`, but `core/` never imports any adapter module.

Isolation is enforced by `tests/test_isolation.py`; running
`pytest tests/test_isolation.py` verifies zero adapter imports in core.

## Installation

````bash
pipx install .
driftmate init
````

**Prerequisite:** an industry-standard dependency-scanning CLI must be
available (installed via npm; the CLI operates in dry-run/lookup mode to
discover dependencies without modifying the repo). `driftmate init` checks
for it and installs it automatically if missing.

## Usage

### Standalone / scan mode (no tokens required)

````bash
driftmate scan [path]
driftmate scan --cve-target helm-chart/Chart.yaml [path]
````

- Produces `driftmate-report.md` in the target directory.
- Does **not** require `GITHUB_TOKEN`, `TELEGRAM_BOT_TOKEN`, or
  `TELEGRAM_CHAT_ID`.
- `--cve-target`: restrict scanning to a specific file/manifest; useful when
  scanning large repos with multiple dependency sources.
- `--cve` (or `--cve-target`, which implies it): enables a container
  vulnerability scan via a vulnerability scanner. This increases runtime
  significantly (~60–120s per image) because it pulls and scans container
  references found in `Dockerfile`. If you only need version-drift
  reporting, omit `--cve`.

### Full mode (human-approved fix via GitHub + Telegram)

````bash
driftmate
````

Requires `GITHUB_TOKEN`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (`.env` or
exported). Runs the full loop: analyze → notify via Telegram → wait for
human approval (inline button) → open a branch and commit the fix on
GitHub → build locally → notify result.

## Report output

`driftmate-report.md` is written to the scanned directory. Example structure
(from a real `nginx` Helm chart scan):

````markdown
# Driftmate Report

**Scanned Path:** `/path/to/repo`
**Scan Timestamp:** `2026-09-23 ... UTC`

## Summary

| Component | File | Current | Target | Severity | CVEs | Field Changes |
|---|---|---|---|---|---|---|
| example-service | Dockerfile | 1.2.0 | 1.3.0 | HIGH | 0C/2H/5M | 3 added, 1 removed |

## Field-Level Changes

### nginx (helm-chart/Chart.yaml) — Field Changes
- Added: automountServiceAccountToken, cloneStaticSiteFromGit.extraEnvVarsSecret, ...
- Removed: resources.limits, resources.requests
- Type changed: resources, ingress, containerSecurityContext, ...

## Text Report

```text
Drift report:
- [DRIFT] nginx (helm-chart/Chart.yaml): 15.0.0 -> 15.14.2 (HIGH)
```
````

Field-level diffs come from comparing upstream `values.yaml` archives
retrieved via the dependency-scanning CLI's real registry metadata (not a
guessed URL).

## Configuration

`config.yaml` (optional): settings for `RepoProvider`, `NotificationChannel`,
`BuildRunner`, severity thresholds, and scan scope.

`.env` (optional): secrets (`GITHUB_TOKEN`, `TELEGRAM_BOT_TOKEN`,
`TELEGRAM_CHAT_ID`). If missing, full-flow commands exit with a clear
error; standalone `scan` mode works without them.

## Component Discovery

Driftmate does not require a `driftmate.yaml` manifest. Instead, it uses a
dependency-scanning CLI (installed via npm, see Installation) to
automatically discover dependencies in your repository across Dockerfiles,
Helm charts, and Terraform modules.

The CLI runs in `--dry-run=lookup` mode and outputs dependency metadata
including `depName`, `currentValue`, `packageFile`, and registry URLs.
Driftmate parses this output to build `DriftReport` objects — no repo state
is modified during discovery.

## Known limitations

- State management is in-memory only (`DriftAnalyzer` holds reports in a
  Python list); no persistent store is wired in V1.
- `push()` adapter is implemented but not wired in the V1 remediation flow;
  builds produce only local images, registry pushes are not performed
  (conscious V1 limitation).
```bash
driftmate scan /path/to/repo
# Standalone, fast — version drift only (no CVE)

driftmate scan --cve /path/to/repo
# Standalone + vulnerability scanning (~60-120s per image)

driftmate scan --cve-target Dockerfile /path/to/repo
# Target single package file; implies --cve

driftmate
# Full mode: Telegram + GitHub, human-approved fix flow
```

- `driftmate scan` produces reports locally only; opening a branch/commit
  requires full mode with a configured `RepoProvider`.

## Development

````bash
pytest
mypy src/driftmate/core/
python -m pytest tests/test_isolation.py
````

Isolation rules are enforced: `core/` must not import `providers/`,
`channels/`, or `build/`.

See `BACKLOG.md` for the V2+ roadmap.