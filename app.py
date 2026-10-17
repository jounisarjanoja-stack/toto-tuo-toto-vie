#!/usr/bin/env python3
"""Toto tuo Toto vie.

Käynnistys: python3 app.py
Avaa: http://127.0.0.1:8011

Render asettaa PORT-ympäristömuuttujan. Palvelin kuuntelee oletuksena
kaikkia osoitteita, jotta julkaisu tavoittaa sen.
"""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import v75

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
PORT = int(os.environ.get("PORT", "8011"))
HOST = os.environ.get("HOST", "0.0.0.0")

FILES = {
    "/": "index.html",
    "/index.html": "index.html",
    "/styles.css": "styles.css",
    "/mobile.css": "mobile.css",
    "/app.js": "app.js",
    "/sulky.svg": "sulky.svg",
}
TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/card":
            self._card()
            return
        name = FILES.get(path)
        if name is None:
            self.send_error(404)
            return
        file_path = STATIC / name
        body = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", TYPES[file_path.suffix])
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _card(self):
        query = parse_qs(urlparse(self.path).query)
        refresh = query.get("refresh", ["0"])[0] == "1"
        raw_card = query.get("card", [""])[0]
        card_id = int(raw_card) if raw_card.isdigit() else None
        game = query.get("game", [""])[0] or None
        raw_race = query.get("race", [""])[0]
        race_number = int(raw_race) if raw_race.isdigit() else None
        try:
            stake = float(query.get("stake", ["0.10"])[0].replace(",", "."))
        except ValueError:
            stake = 0.10
        try:
            payload = v75.build(
                card_id=card_id,
                refresh=refresh,
                stake=stake,
                game=game,
                race_number=race_number,
            )
            status = 200
        except Exception as error:
            payload = {"error": f"Kohteita ei saatu haettua: {error}"}
            status = 502
            print(payload["error"])
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} {fmt % args}")


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    shown = "127.0.0.1" if HOST in ("0.0.0.0", "::") else HOST
    print(f"Toto tuo Toto vie: http://{shown}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
