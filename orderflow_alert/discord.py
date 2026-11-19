"""Optional: also post every alert to a Discord channel through a bot, and mention a user."""

from __future__ import annotations

import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

API = "https://discord.com/api/v10"


def read_token(path: str) -> str:
    """The bot token from a file: either an env-style line DISCORD_BOT_TOKEN=... or the token alone."""
    text = Path(path).expanduser().read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("DISCORD_BOT_TOKEN="):
            return line.split("=", 1)[1].strip().strip("\"'")
    return text.strip()


class DiscordPoster:
    def __init__(self, channel_id: str, token_file: str, mention: str = ""):
        self.url = f"{API}/channels/{channel_id}/messages"
        self.token = read_token(token_file)
        if not self.token:
            raise SystemExit(f"No Discord bot token in {token_file}")
        self.mention = mention

    def payload(self, text: str) -> dict:
        if self.mention:
            return {"content": f"<@{self.mention}> {text}", "allowed_mentions": {"users": [self.mention]}}
        return {"content": text, "allowed_mentions": {"parse": []}}

    def send(self, text: str) -> bool:
        req = urllib.request.Request(self.url, data=json.dumps(self.payload(text)).encode(), method="POST",
                                     headers={"Authorization": f"Bot {self.token}", "Content-Type": "application/json",
                                              "User-Agent": "DiscordBot (orderflow-alert, 0.1)"})
        try:
            with urllib.request.urlopen(req, timeout=15):
                return True
        except (urllib.error.URLError, OSError) as exc:
            print(f"discord post failed: {exc}", file=sys.stderr, flush=True)
            return False

    def post(self, text: str) -> None:
        """Send in the background, so a slow Discord never holds up the bar stream."""
        threading.Thread(target=self.send, args=(text,), daemon=True).start()
