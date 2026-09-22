"""Interactive initialization command ('driftmate init').

Guides the user step-by-step through setting up GITHUB_TOKEN, TELEGRAM_BOT_TOKEN,
and automatically fetches TELEGRAM_CHAT_ID via Bot API getUpdates.
Checks Docker daemon health and writes the .env file.
"""

import getpass
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from typing import Optional

from driftmate.core.services.renovate_runner import RenovateRunner


def _check_renovate():
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
            print("Run 'npm install -g renovate' manually and try again.")
            sys.exit(1)
            
        if not runner.check_health():
            print("Setup incomplete: Renovate validation failed.")
            print("Run 'npm install -g renovate' manually and try again.")
            sys.exit(1)

    except Exception as e:
        print(f"Error during Renovate installation: {e}")
        sys.exit(1)


def run_init() -> None:
    print("=== Driftmate Interactive Setup ===\n")

    # 0. Renovate Check
    _check_renovate()

    # 1. GitHub Token
    print("Step 1: GitHub Personal Access Token")
    print("  1. GitHub -> Settings -> Developer settings -> Personal access tokens")
    print("  2. Select 'Fine-grained tokens' -> Generate new token")
    print("  3. Repository access: Only select this repository (driftmate)")
    print("  4. Permissions -> Contents -> Read and write")
    github_token = getpass.getpass("Enter GITHUB_TOKEN: ").strip()
    if not github_token:
        print("Error: GITHUB_TOKEN cannot be empty.")
        return

    # 2. Telegram Bot Token
    print("\nStep 2: Telegram Bot Token")
    print("  1. Open Telegram and search for @BotFather")
    print("  2. Send /newbot and follow instructions (name and username ending in 'bot')")
    print("  3. Copy the HTTP API token provided by BotFather")
    telegram_bot_token = getpass.getpass("Enter TELEGRAM_BOT_TOKEN: ").strip()
    if not telegram_bot_token:
        print("Error: TELEGRAM_BOT_TOKEN cannot be empty.")
        return

    # 3. Telegram Chat ID (automatic fetch via getUpdates)
    print("\nStep 3: Telegram Chat ID (Automatic Detection)")
    print("  1. Open Telegram and go to your newly created bot chat")
    print("  2. Send any message to the bot (e.g., 'hello' or 'hi')")
    input("Press Enter once you have sent the message to the bot... ")

    chat_id: Optional[str] = None
    url = f"https://api.telegram.org/bot{telegram_bot_token}/getUpdates"

    for attempt in range(1, 6):
        print(f"Fetching updates from Telegram (attempt {attempt}/5)...")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Driftmate-Init"})
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
                if data.get("ok"):
                    results = data.get("result", [])
                    if results:
                        # Get the latest message/chat id
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
        chat_id = input("Please enter TELEGRAM_CHAT_ID manually: ").strip()

    if not chat_id:
        print("Error: TELEGRAM_CHAT_ID cannot be empty.")
        return

    # 4. Check Docker daemon
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

    # 5. Write .env file
    env_path = ".env"
    if os.path.exists(env_path):
        overwrite = input(f"'{env_path}' already exists. Overwrite? [y/N]: ").strip().lower()
        if overwrite not in ("y", "yes"):
            print("Setup cancelled (.env not changed).")
            return

    env_content = f"""# Driftmate Environment Configuration
# Generated by 'driftmate init'

GITHUB_TOKEN={github_token}
TELEGRAM_BOT_TOKEN={telegram_bot_token}
TELEGRAM_CHAT_ID={chat_id}
"""

    with open(env_path, "w", encoding="utf-8") as f:
        f.write(env_content)

    os.chmod(env_path, 0o600)

    print(f"\n[SUCCESS] '{env_path}' created successfully!")
    print("You can now start Driftmate with 'driftmate'.")
