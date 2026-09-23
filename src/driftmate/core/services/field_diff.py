"""Mechanical field-level diff for Helm values and Terraform variables.

Pure Python, no LLM calls. Compares two YAML dicts at top-level and one
level of nested keys to produce added/removed/type_changed summaries.
"""

import logging
import tempfile
import tarfile
import io
from dataclasses import dataclass, field
from typing import Any, Optional

import urllib.request
import yaml
import requests

logger = logging.getLogger(__name__)


@dataclass
class FieldDiff:
    """Summary of added/removed/type-changed keys between two YAML dicts."""
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    type_changed: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.added or self.removed or self.type_changed)

    def summary(self) -> str:
        """Short summary string for table display."""
        parts = []
        if self.added:
            parts.append(f"{len(self.added)} added")
        if self.removed:
            parts.append(f"{len(self.removed)} removed")
        if self.type_changed:
            parts.append(f"{len(self.type_changed)} type changed")
        return ", ".join(parts) if parts else "-"


def _flatten_keys(d: dict, prefix: str = "") -> dict[str, Any]:
    """Flatten one level of nested dicts into dotted keys.

    Both parent dict keys and their immediate children are kept so that
    type changes (dict vs scalar) can be detected at the parent level.
    """
    result: dict[str, Any] = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        # Always keep the key itself
        result[key] = v
        if isinstance(v, dict):
            for sk, sv in v.items():
                result[f"{key}.{sk}"] = sv
    return result


def diff_dicts(old: Optional[dict], new: Optional[dict]) -> FieldDiff:
    """Compare two dicts, returning added/removed/type_changed keys.

    Compares at top-level and one level of nested keys (flattened).
    """
    if old is None:
        old = {}
    if new is None:
        new = {}

    old_flat = _flatten_keys(old)
    new_flat = _flatten_keys(new)

    diff = FieldDiff()
    old_keys = set(old_flat.keys())
    new_keys = set(new_flat.keys())

    diff.added = sorted(new_keys - old_keys)
    diff.removed = sorted(old_keys - new_keys)

    for k in old_keys & new_keys:
        old_val = old_flat[k]
        new_val = new_flat[k]
        if type(old_val) != type(new_val):
            # Type changed at this level
            diff.type_changed.append(k)
        elif isinstance(old_val, dict) and isinstance(new_val, dict):
            # Compare nested dicts recursively one level
            sub_diff = diff_dicts(old_val, new_val)
            if not sub_diff.is_empty():
                # Report the parent key as type_changed if the sub-diff is non-empty
                # (the sub-diff details are captured in added/removed/type_changed
                # of the parent, but for summary we mark the parent)
                diff.type_changed.append(k)

    return diff


def fetch_helm_values(chart_repo: str, chart_name: str, version: str) -> Optional[dict]:
    """Fetch values.yaml from a Helm chart repo.

    Returns parsed YAML dict or None on failure.
    """
    url = f"{chart_repo.rstrip('/')}/{chart_name}-{version}.tgz"
    logger.debug("Fetching Helm chart archive: %s", url)
    try:
        resp = requests.get(url, headers={"User-Agent": "Driftmate-FieldDiff/1.0"}, timeout=30, allow_redirects=True)
        if resp.status_code != 200:
            logger.warning("Failed to fetch Helm values for %s %s: HTTP %d", chart_name, version, resp.status_code)
            return None
        data = resp.content
        with tempfile.SpooledTemporaryFile() as tmp:
            tmp.write(data)
            tmp.seek(0)
            with tarfile.open(fileobj=tmp, mode="r:gz") as tar:
                for member in tar.getmembers():
                    if member.name.endswith("/values.yaml") or member.name == "values.yaml":
                        f = tar.extractfile(member)
                        if f:
                            content = f.read().decode("utf-8")
                            return yaml.safe_load(content)
    except Exception as exc:
        logger.warning("Failed to fetch Helm values for %s %s: %s", chart_name, version, exc)
        return None
    return None


def fetch_terraform_vars(module_url: str, version: str) -> Optional[dict]:
    """Fetch variables.tf from Terraform Registry module.

    Returns parsed YAML dict or None on failure.
    """
    url = f"{module_url.rstrip('/')}/v{version}/variables.tf"
    logger.debug("Fetching Terraform variables: %s", url)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Driftmate-FieldDiff/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read().decode("utf-8")
            # Parse HCL variables block (simple regex-based extraction)
            import re
            var_blocks = re.findall(
                r'variable\s+"([^"]+)"\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}',
                content,
                re.DOTALL,
            )
            result: dict[str, Any] = {}
            for name, body in var_blocks:
                type_match = re.search(r'type\s*=\s*(\S+)', body)
                default_match = re.search(r'default\s*=\s*(.+?)(?:\n|$)', body)
                result[name] = {
                    "type": type_match.group(1) if type_match else "any",
                    "default": default_match.group(1).strip() if default_match else None,
                }
            return result if result else None
    except Exception as exc:
        logger.warning("Failed to fetch Terraform vars for %s %s: %s", module_url, version, exc)
        return None


def compute_field_diff(
    dep_name: str,
    datasource: str,
    current_value: str,
    new_value: Optional[str],
    package_file: str,
    chart_repo: str,
) -> Optional[FieldDiff]:
    """Compute field diff for a dependency based on its type.

    Returns None for Docker (no field diff) or on fetch failure.
    """
    if datasource == "docker":
        return None

    if datasource == "helm" or (datasource in ("unknown",) and package_file and package_file.endswith("Chart.yaml")):
        if not chart_repo:
            return None
        chart_name = dep_name.split("/")[-1]
        old_values = fetch_helm_values(chart_repo, chart_name, current_value)
        if new_value:
            new_values = fetch_helm_values(chart_repo, chart_name, new_value)
        else:
            new_values = None
        if old_values is None or new_values is None:
            return None
        return diff_dicts(old_values, new_values)

    if datasource == "terraform-module" or datasource == "terraform-provider":
        # Try to fetch from Terraform Registry
        module_url = f"https://registry.terraform.io/v1/modules/{dep_name}"
        old_vars = fetch_terraform_vars(module_url, current_value)
        if new_value:
            new_vars = fetch_terraform_vars(module_url, new_value)
        else:
            new_vars = None
        if old_vars is None or new_vars is None:
            return None
        return diff_dicts(old_vars, new_vars)

    return None