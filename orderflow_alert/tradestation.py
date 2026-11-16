"""Minimal read-only TradeStation API v3 client (stdlib only) plus a one-time OAuth login command.

Market data only: the login asks for the MarketData scope and nothing else, so these credentials
cannot see account balances, positions or orders, and cannot place, change or cancel anything.

Credentials live in ~/Library/Application Support/orderflow-alert/tradestation.json (mode 0600):
{"client_id": ..., "client_secret": ..., "refresh_token": ...}. Run `orderflow-login` once to create it.
"""

from __future__ import annotations

import argparse
import getpass
import http.server
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

LIVE_URL = "https://api.tradestation.com/v3"
SIGNIN_URL = "https://signin.tradestation.com"
REDIRECT_URI = "http://localhost:3000"  # preconfigured on every TradeStation API key
SCOPES = "openid offline_access MarketData"
SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "orderflow-alert"
CREDENTIALS = SUPPORT_DIR / "tradestation.json"


class TradeStationError(RuntimeError):
    pass


def _request(method: str, url: str, *, headers: dict | None = None, body: bytes | None = None, timeout: float = 30) -> dict:
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            text = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise TradeStationError(f"{method} {url} -> HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:500]}") from exc
    return json.loads(text) if text else {}


def _token_request(fields: dict) -> dict:
    body = urllib.parse.urlencode(fields).encode()
    return _request("POST", f"{SIGNIN_URL}/oauth/token", headers={"Content-Type": "application/x-www-form-urlencoded"}, body=body)


def save_credentials(creds: dict, path: Path = CREDENTIALS) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(creds, f)


class TradeStationClient:
    def __init__(self, base_url: str = LIVE_URL, credentials_path: Path = CREDENTIALS):
        self.base_url = base_url
        self.credentials_path = credentials_path
        self.creds = json.loads(credentials_path.read_text())
        self._access_token = ""
        self._expires_at = 0.0

    def _token(self) -> str:
        if time.time() < self._expires_at - 60:
            return self._access_token
        data = _token_request({"grant_type": "refresh_token", "client_id": self.creds["client_id"],
                               "client_secret": self.creds["client_secret"], "refresh_token": self.creds["refresh_token"]})
        if data.get("refresh_token") and data["refresh_token"] != self.creds["refresh_token"]:  # rotating refresh tokens
            self.creds["refresh_token"] = data["refresh_token"]
            save_credentials(self.creds, self.credentials_path)
        self._access_token = data["access_token"]
        self._expires_at = time.time() + float(data.get("expires_in", 1200))
        return self._access_token

    def stream_bars(self, symbol: str, barsback: int):
        """Yield 1-minute bar messages: the last `barsback` bars, then the open bar again on every tick (about 4 a second)."""
        query = urllib.parse.urlencode({"interval": "1", "unit": "Minute", "barsback": str(barsback)})
        req = urllib.request.Request(f"{self.base_url}/marketdata/stream/barcharts/{urllib.parse.quote(symbol, safe='')}?{query}",
                                     headers={"Authorization": f"Bearer {self._token()}"})
        with urllib.request.urlopen(req, timeout=30) as response:  # a silent stall raises after 30 s
            for line in response:
                if line.strip():
                    yield json.loads(line)


def _capture_code(state: str) -> str:
    result: dict[str, str] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (stdlib name)
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if query.get("state", [""])[0] == state and "code" in query:
                result["code"] = query["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("TradeStation login received. You can close this tab.".encode() if "code" in result else b"Login failed.")

        def log_message(self, *_args):
            pass

    with http.server.HTTPServer(("localhost", 3000), Handler) as server:
        while "code" not in result:
            server.handle_request()
    return result["code"]


def login_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="orderflow-login", description="Authorize market-data access to TradeStation (one time).")
    parser.add_argument("--reset", action="store_true", help="ask for the API key and secret again")
    args = parser.parse_args(argv)
    creds = {} if args.reset or not CREDENTIALS.exists() else json.loads(CREDENTIALS.read_text())
    if not creds.get("client_id"):
        creds["client_id"] = input("TradeStation API key (client_id): ").strip()
        creds["client_secret"] = getpass.getpass("TradeStation API secret (hidden): ").strip()
    state = secrets.token_urlsafe(16)
    url = f"{SIGNIN_URL}/authorize?" + urllib.parse.urlencode({"response_type": "code", "client_id": creds["client_id"], "audience": "https://api.tradestation.com",
                                                               "redirect_uri": REDIRECT_URI, "scope": SCOPES, "state": state})
    print(f"Opening the TradeStation sign-in page. If it does not open, visit:\n{url}", file=sys.stderr)
    webbrowser.open(url)
    code = _capture_code(state)
    tokens = _token_request({"grant_type": "authorization_code", "client_id": creds["client_id"], "client_secret": creds["client_secret"],
                             "code": code, "redirect_uri": REDIRECT_URI})
    creds["refresh_token"] = tokens["refresh_token"]
    save_credentials(creds)
    print(f"Saved credentials to {CREDENTIALS}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(login_main())
