# Driftmate — V2+ Roadmap

- Persistent state store (Redis/SQLite)
- The `push()` adapter is implemented but not wired in the V1 remediation flow; builds only produce local images, and registry pushes are not performed (conscious V1 limitation).
- **Azure DevOps RepoProvider (V2 feasibility):** Azure DevOps REST API — `getFile` via `GET /{project}/_apis/git/repositories/{repositoryId}/items?path=...`. The `createBranch`, `commitFile`, and `publishBranch` methods cannot be called separately as in GitHub; in Azure DevOps, all are performed via a **single pushes endpoint**: `POST /{project}/_apis/git/repositories/{repositoryId}/pushes` (apiVersion 7.0+). The request body includes `refUpdates` (branch name + old commit SHA) and `commits[].changes[]` (file path, changeType: `add`/`edit`/`delete`, content). PAT scope: `Code (Read/Write)` (`vso.code_write`). The ADO adapter must combine the three separate methods of the Protocol interface into this single push call.
- **Slack NotificationChannel (V2 feasibility):** `sendMessage` → `chat.postMessage`; `updateMessage` → `chat.update`; `onAction` → **Socket Mode** for interactive button feedback (no public HTTPS endpoint / ngrok required, works from WSL2 — same model as Telegram polling). Slack Socket Mode is WebSocket-based; whereas Telegram uses long-polling + `update.callback_query`, Slack uses `SocketModeHandler` to listen for `interactivity` events.
- AI risk report, Slack, Azure DevOps, AWS CodeBuild
- Kubernetes manifest drift analysis
- Webhook-based notification instead of long-polling
- CI/CD integration (auto-trigger on branch merge)
- Docker containerization (requires mounting `docker.sock` and a volume for `git worktree` paths if running inside a container).
- Cache dizinini periyodik temizleme / stale-lock kontrolü ekleme (renovate_runner health-check)
- mypy cleanup needed in field_diff.py and scan_cmd.py (5 errors each, introduced during CVE/field-diff work) — not pre-existing, deferred for now.
