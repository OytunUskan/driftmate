"""Interactive initialization command ('driftmate init').

Guides the user through mode selection (full vs standalone) and setup.
Checks dependency-scanning CLI + Docker health; writes .env only when needed.
"""

import getpass
import os
import shutil
import subprocess
import sys
import time
from typing import Optional

from driftmate.core.services.renovate_runner import RenovateRunner
from driftmate.core.services.trivy_runner import TrivyRunner


def _check_dependency_scanning():
    if not shutil.which("npm"):
        print("Error: Node.js/npm not found. Required for dependency scanning.")
        print("Installation: https://github.com/nvm-sh/nvm")
        sys.exit(1)

    runner = RenovateRunner()
    if runner.check_health():
        return

    try:
        process = subprocess.Popen(
            ["npm", "install", "-g", "renovate"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        process.communicate()
        if process.returncode != 0:
            print("Setup incomplete: a required dependency-scanning tool could not be installed automatically.")
            print("Run 'npm install -g dependency-scanning-cli' manually and try again.")
            sys.exit(1)
        if not runner.check_health():
            print("Setup incomplete: dependency-scanning validation failed.")
            print("Run 'npm install -g dependency-scanning-cli' manually and try again.")
            sys.exit(1)
    except Exception as e:
        print(f"Error during dependency-scanning installation: {e}")
        sys.exit(1)


def run_init() -> None:
    print("=== Driftmate Interactive Setup ===\n")

    # Dependency-scanning check (silent on success)
    _check_dependency_scanning()

    # Optional vulnerability-scanner check
    try:
        scanner = TrivyRunner()
        if not scanner.check_health():
            print("Warning: vulnerability scanner CLI not installed. CVE scanning unavailable.")
    except Exception:
        pass

    # Mode selection
    print("Choose setup mode:")
    print("  [1] Full mode  — GitHub + Telegram (human-approved fix flow)")
    print("  [2] Standalone only (default) — scan-only, no tokens required")
    mode_choice = input("Select mode [1/2] (default 2): ").strip()
    full_mode = (mode_choice == "1")

    github_token = ""
    telegram_bot_token = ""
    chat_id = ""

    if full_mode:
        # 1. GitHub Token (optional — blank allowed with warning)
        print("\nStep 1: GitHub Personal Access Token (optional — leave blank if using standalone)")
        github_token = getpass.getpass("Enter GITHUB_TOKEN (blank = full mode disabled until set): ").strip()
        if not github_token:
            print("GITHUB_TOKEN left blank — full remediation mode will not work until this is set; you can still use 'driftmate scan'.")

        # 2. Telegram Bot Token (optional — blank allowed with warning)
        print("\nStep 2: Telegram Bot Token (optional — leave blank if using standalone)")
        telegram_bot_token = getpass.getpass("Enter TELEGRAM_BOT_TOKEN (blank = full mode disabled until set): ").strip()
        if not telegram_bot_token:
            print("TELEGRAM_BOT_TOKEN left blank — full remediation mode will not work until this is set; you can still use 'driftmate scan'.")

        # 3. Telegram Chat ID — only if bot token actually provided
        if telegram_bot_token:
            print("\nStep 3: Telegram Chat ID (Automatic Detection)")
            url = f"https://api.telegram.org/bot{telegram_bot_token}/getUpdates"
            chat_id = None
            for attempt in range(1, 6):
                print(f"Fetching updates from Telegram (attempt {attempt}/5)...")
                try:
                    import urllib.request, json
                    req = urllib.request.Request(url, headers={"User-Agent": "Driftmate-Init"})
                    with urllib.request.urlopen(req, timeout=10) as response:
                        data = json.loads(response.read().decode("utf-8"))
                        if data.get("ok"):
                            results = data.get("result", [])
                            if results:
                                latest = results[-1]
                                msg = latest.get("message") or latest.get("edited_message") or latest.get("channel_post")
                                if msg and "chat" in msg:
                                    chat_id = str(msg["chat"]["id"])
                                    break
                except Exception as exc:
                    print(f"  Warning: Failed to reach Telegram API: {exc}")
                if not chat_id and attempt < 5:
                    input("Message not found. Send another message to the bot and press Enter...")
            if chat_id:
                confirm = input(f"Found: chat_id = {chat_id}, is this correct? [Y/n]: ").strip().lower()
                if confirm in ("n", "no"):
                    chat_id = input("Please enter TELEGRAM_CHAT_ID manually: ").strip()
            else:
                print("Automatic chat_id detection failed.")
                chat_id = input("Please enter TELEGRAM_CHAT_ID manually (leave blank to skip): ").strip()
        else:
            print("\nStep 3: Telegram Chat ID skipped (no bot token provided).")
    else:
        print("\nStandalone mode selected — no tokens required.")

    # 4. Docker check
    print("\nStep 4: Checking Docker Daemon health...")
    docker_ok = False
    try:
        res = subprocess.run(["docker", "ps"], capture_output=True, text=True, timeout=5, check=False)
        if res.returncode == 0:
            docker_ok = True
            print("  [OK] Docker daemon is active and accessible.")
        else:
            print(f"  [WARNING] docker ps returned non-zero code: {res.stderr.strip()}")
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        print(f"  [WARNING] Docker daemon could not be accessed ({exc}).")

    if not docker_ok:
        print("\n  [WARNING] Docker daemon could not be accessed.")
        print("  Ensure Docker Desktop / WSL integration is enabled and `docker ps` works.")
        print("  (Local Docker build steps require the Docker daemon.)\n")

    # 5. Write .env (only if anything to write, or always with blanks for full mode)
    env_path = ".env"
    if os.path.exists(env_path):
        overwrite = input(f"'{env_path}' already exists. Overwrite? [y/N]: ").strip().lower()
        if overwrite not in ("y", "yes"):
            print("Setup completed without changing .env.")
            return

    env_lines = [
        "# Driftmate Environment Configuration",
        "# Generated by 'driftmate init'",
        "",
    ]
    if github_token or full_mode:
        env_lines.append(f"GITHUB_TOKEN={github_token}")
    if telegram_bot_token or full_mode:
        env_lines.append(f"TELEGRAM_BOT_TOKEN={telegram_bot_token}")
    if chat_id or (full_mode and telegram_bot_token):
        env_lines.append(f"TELEGRAM_CHAT_ID={chat_id}")

    env_content = "\n".join(env_lines) + "\n"

    with open(env_path, "w", encoding="utf-8") as f:
        f.write(env_content)

    os.chmod(env_path, 0o600)
    print(f"\n[SUCCESS] '{env_path}' created successfully!")
    print("You can now use 'driftmate scan' (standalone) or 'driftmate' (full mode when tokens are configured).")
