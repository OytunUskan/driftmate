"""Renovate CLI execution and result parsing."""

import json
import logging
import os
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class RenovateError(Exception):
    """Raised when Renovate execution fails."""


@dataclass
class RenovateDependency:
    name: str
    package_name: str
    current_value: str
    datasource: str
    package_file: str
    new_value: str | None = None
    update_type: str | None = None


@dataclass
class RenovateResult:
    dependencies: list[RenovateDependency] = field(default_factory=list)


class RenovateRunner:
    _lock = threading.Lock()

    def __init__(self, binary_path: str | None = None) -> None:
        self._binary = binary_path or shutil.which("renovate")

    def check_health(self) -> bool:
        """Verify Renovate is installed and functional."""
        if not self._binary:
            return False
        try:
            subprocess.run(
                [self._binary, "--version"],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            return True
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    def run_lookup(self, repo_path: str) -> RenovateResult:
        """Run Renovate in dry-run lookup mode and parse the dependencies found."""
        if not self._lock.acquire(blocking=False):
            raise RenovateError("Bir analiz zaten sürüyor, lütfen bitmesini bekleyin.")

        try:
            return self._execute_lookup(repo_path)
        finally:
            self._lock.release()

    def _execute_lookup(self, repo_path: str) -> RenovateResult:
        if not self._binary:
            raise RenovateError(
                "Renovate CLI not found. Please install it with 'npm install -g renovate'."
            )

        cache_dir = Path("/tmp/renovate-cache")
        cache_dir.mkdir(parents=True, exist_ok=True)

        env = os.environ.copy()
        env["REPOSITORIES"] = json.dumps([repo_path])
        env["LOG_LEVEL"] = "debug"

        cmd = [
            self._binary,
            "--platform=local",
            "--dry-run=lookup",
            "--enabled-managers=dockerfile,helmv3,terraform",
            "--cache-dir",
            str(cache_dir),
        ]

        logger.debug("Executing Renovate: %s in %s", " ".join(cmd), repo_path)
        try:
            result = subprocess.run(
                cmd,
                cwd=repo_path,
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired as exc:
            raise RenovateError("Renovate execution timed out after 120s") from exc
        except subprocess.SubprocessError as exc:
            raise RenovateError(f"Renovate execution failed: {exc}") from exc

        if result.returncode != 0:
            logger.error("Renovate stderr: %s", result.stderr)
            raise RenovateError(f"Renovate failed with exit code {result.returncode}")

        return self._parse_renovate_output(result.stdout + result.stderr)

    def _parse_renovate_output(self, output: str) -> RenovateResult:
        """Parse Renovate debug logs to extract dependency information."""
        dependencies: list[RenovateDependency] = []
        lines = output.splitlines()
        
        config_data = None
        for i, line in enumerate(lines):
            if "packageFiles with updates" in line:
                json_lines = []
                for j in range(i + 1, len(lines)):
                    sub_line = lines[j]
                    if sub_line.strip().startswith('"config":') or sub_line.startswith("       ") or sub_line.startswith("      "):
                        json_lines.append(sub_line)
                    elif not sub_line.strip():
                        continue
                    else:
                        if "DEBUG:" in sub_line or "INFO:" in sub_line or "WARN:" in sub_line:
                            break
                        json_lines.append(sub_line)
                
                if json_lines:
                    combined = "\n".join(json_lines)
                    if not combined.strip().startswith("{"):
                        combined = "{\n" + combined + "\n}"
                    try:
                        data = json.loads(combined)
                        config = data.get("config", {})
                        self._extract_from_config(config, dependencies)
                        config_data = config
                        break
                    except json.JSONDecodeError:
                        pass

        if not config_data:
            logger.warning("Could not parse 'packageFiles with updates' JSON block from Renovate output.")

        return RenovateResult(dependencies=dependencies)

    def _extract_from_config(self, config: dict[str, Any], deps_list: list[RenovateDependency]) -> None:
        """Helper to walk the Renovate config object and extract dependencies."""
        for manager, files in config.items():
            if not isinstance(files, list):
                continue
            for f in files:
                package_file = f.get("packageFile", "unknown")
                for dep in f.get("deps", []):
                    name = dep.get("depName")
                    curr = dep.get("currentValue")
                    if not name or not curr:
                        continue
                    
                    new_val = None
                    upd_type = None
                    updates = dep.get("updates", [])
                    if updates:
                        update = updates[0]
                        new_val = update.get("newValue") or update.get("newVersion")
                        upd_type = update.get("updateType")

                    deps_list.append(
                        RenovateDependency(
                            name=name,
                            package_name=dep.get("packageName", name),
                            current_value=curr,
                            datasource=dep.get("datasource", "unknown"),
                            package_file=package_file,
                            new_value=new_val,
                            update_type=upd_type
                        )
                    )
