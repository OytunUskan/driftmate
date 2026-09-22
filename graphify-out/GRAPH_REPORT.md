# Graph Report - driftmate  (2026-09-22)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 209 nodes · 466 edges · 16 communities (8 shown, 8 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 34 edges (avg confidence: 0.95)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `16a7547e`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- drift_analyzer.py
- RepoProvider
- telegram_channel.py
- TelegramNotificationChannel
- loader.py
- remediation_orchestrator.py
- main.py
- RemediationOrchestrator
- graphify.js
- core/__init__.py
- driftmate/__init__.py
- driftmate

## God Nodes (most connected - your core abstractions)
1. `TelegramNotificationChannel` - 21 edges
2. `RemediationOrchestrator` - 20 edges
3. `RepoProvider` - 18 edges
4. `Content` - 15 edges
5. `Action` - 15 edges
6. `GitHubRepoProvider` - 14 edges
7. `compare_versions()` - 14 edges
8. `InMemoryStateStore` - 12 edges
9. `DriftAnalyzer` - 11 edges
10. `NotificationChannel` - 11 edges

## Surprising Connections (you probably didn't know these)
- `test_telegram_channel_registers_analyze_and_action()` --uses--> `TelegramNotificationChannel`  [INFERRED]
  tests/test_telegram_channel.py → src/driftmate/channels/telegram/telegram_channel.py
- `test_format_report_statuses()` --uses--> `DriftReport`  [INFERRED]
  tests/test_remediation.py → src/driftmate/core/services/drift_analyzer.py
- `TestCompareVersions` --uses--> `Severity`  [INFERRED]
  tests/test_drift_analyzer.py → src/driftmate/core/services/drift_analyzer.py
- `TestExtractVersion` --uses--> `Content`  [INFERRED]
  tests/test_drift_analyzer.py → src/driftmate/core/models/repo.py
- `test_telegram_channel_registers_analyze_and_action()` --uses--> `InMemoryStateStore`  [INFERRED]
  tests/test_telegram_channel.py → src/driftmate/channels/common/state_store.py

## Import Cycles
- None detected.

## Communities (16 total, 8 thin omitted)

### Community 0 - "drift_analyzer.py"
Cohesion: 0.10
Nodes (22): dataclasses, compare_versions(), ComponentSpec, DriftAnalyzer, DriftReport, Manifest, ManifestError, ManifestNotFoundError (+14 more)

### Community 1 - "RepoProvider"
Cohesion: 0.11
Nodes (18): base64, github, github_githubexception, logging, build_repo_provider_factory(), factory(), Protocol, RepoProvider (+10 more)

### Community 2 - "telegram_channel.py"
Cohesion: 0.10
Nodes (14): asyncio, concurrent_futures, InMemoryStateStore, Any, Protocol, Shared state store for channel adapters. Holds the short-ID -> context mapping…, StateStore, Telegram implementation of the NotificationChannel interface. Uses python-… (+6 more)

### Community 3 - "TelegramNotificationChannel"
Cohesion: 0.16
Nodes (8): DEFAULT_TYPE, InlineKeyboardMarkup, TelegramNotificationChannel, NotificationChannel, Protocol, Action, MessageRef, Update

### Community 4 - "loader.py"
Cohesion: 0.21
Nodes (19): pytest, AppConfig, build_config(), BuildConfig, ConfigError, load_config(), _lookup_env(), Any (+11 more)

### Community 5 - "remediation_orchestrator.py"
Cohesion: 0.21
Nodes (10): datetime, ruamel_yaml, ruamel_yaml_scalarstring, BuildRunner, Protocol, BuildResult, Enum, Status (+2 more)

### Community 6 - "main.py"
Cohesion: 0.14
Nodes (16): argparse, dotenv, driftmate_build_local_docker_runner, getpass, json, os, pathlib, Interactive initialization command ('driftmate init'). Guides the user step-by-… (+8 more)

### Community 8 - "graphify.js"
Cohesion: 0.40
Nodes (3): IMPORTANT: keep the reminder string free of backticks and $(...) constructs., ref_fs, ref_path

## Knowledge Gaps
- **1 isolated node(s):** `driftmate`
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 67 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **8 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `TelegramNotificationChannel` connect `TelegramNotificationChannel` to `telegram_channel.py`, `main.py`?**
  _High betweenness centrality (0.124) - this node is a cross-community bridge._
- **Why does `RemediationOrchestrator` connect `RemediationOrchestrator` to `drift_analyzer.py`, `RepoProvider`, `TelegramNotificationChannel`, `remediation_orchestrator.py`, `main.py`?**
  _High betweenness centrality (0.095) - this node is a cross-community bridge._
- **Are the 5 inferred relationships involving `TelegramNotificationChannel` (e.g. with `InMemoryStateStore` and `StateStore`) actually correct?**
  _`TelegramNotificationChannel` has 5 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `RemediationOrchestrator` (e.g. with `BuildRunner` and `NotificationChannel`) actually correct?**
  _`RemediationOrchestrator` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 6 inferred relationships involving `RepoProvider` (e.g. with `build_repo_provider_factory()` and `Branch`) actually correct?**
  _`RepoProvider` has 6 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `Content` (e.g. with `RepoProvider` and `extract_version()`) actually correct?**
  _`Content` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 3 inferred relationships involving `Action` (e.g. with `TelegramNotificationChannel` and `NotificationChannel`) actually correct?**
  _`Action` has 3 INFERRED edges - model-reasoned connections that need verification._