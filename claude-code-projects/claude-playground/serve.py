#!/usr/bin/env python3
"""Voice Chat – proxy server for STT, TTS, and LLM services.

Serves the UI and proxies API calls to local Docker services
(Parakeet STT, Magpie TTS) and a local OpenAI-compatible LLM,
avoiding CORS issues.

Usage:
    python3 serve.py                         # defaults
    PORT=3000 python3 serve.py               # custom port
    LLM_URL=http://localhost:8000 python3 serve.py  # custom LLM endpoint
"""

import http.client
import http.server
import json
import os
import ssl
import urllib.parse
from pathlib import Path

PORT = int(os.environ.get("PORT", 8080))
STT_HOST = os.environ.get("STT_HOST", "localhost:9002")
TTS_HOST = os.environ.get("TTS_HOST", "localhost:9000")
LLM_URL = os.environ.get("LLM_URL", "http://localhost:8000")


class VoiceChatHandler(http.server.SimpleHTTPRequestHandler):
    """Serves static files and proxies API calls."""

    def do_GET(self):
        if self.path.endswith(".pem"):
            self.send_error(403, "Forbidden")
            return
        if self.path == "/":
            self.path = "/voice-chat.html"
        if self.path == "/api/health":
            return self._health()
        if self.path == "/api/voices":
            return self._proxy_get(TTS_HOST, "/v1/audio/list_voices")
        if self.path == "/api/config":
            return self._config()
        if self.path == "/api/models":
            return self._proxy_llm_get("/v1/models")
        return super().do_GET()

    def do_POST(self):
        if self.path == "/api/stt":
            return self._proxy_raw(STT_HOST, "/v1/audio/transcriptions")
        if self.path == "/api/tts":
            return self._proxy_raw(TTS_HOST, "/v1/audio/synthesize")
        if self.path == "/api/chat":
            return self._proxy_chat()
        self.send_error(404)

    # ── Proxies ──────────────────────────────────────────────

    def _proxy_raw(self, host, path):
        """Forward multipart body + Content-Type, return full response."""
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        ct = self.headers.get("Content-Type", "application/octet-stream")
        try:
            conn = http.client.HTTPConnection(host, timeout=120)
            conn.request("POST", path, body=body, headers={"Content-Type": ct})
            resp = conn.getresponse()
            data = resp.read()
            self._send(
                resp.status,
                resp.getheader("Content-Type", "application/octet-stream"),
                data,
            )
            conn.close()
        except Exception as exc:
            self._send(502, "application/json", json.dumps({"error": str(exc)}).encode())

    def _proxy_get(self, host, path):
        try:
            conn = http.client.HTTPConnection(host, timeout=10)
            conn.request("GET", path)
            resp = conn.getresponse()
            data = resp.read()
            self._send(resp.status, "application/json", data)
            conn.close()
        except Exception as exc:
            self._send(502, "application/json", json.dumps({"error": str(exc)}).encode())

    def _proxy_llm_get(self, path):
        """Proxy GET to the LLM server."""
        parsed = urllib.parse.urlparse(LLM_URL)
        host = parsed.netloc or parsed.path
        try:
            conn = http.client.HTTPConnection(host, timeout=10)
            conn.request("GET", path)
            resp = conn.getresponse()
            data = resp.read()
            self._send(resp.status, "application/json", data)
            conn.close()
        except Exception as exc:
            self._send(502, "application/json", json.dumps({"error": str(exc)}).encode())

    def _proxy_chat(self):
        """Stream OpenAI-compatible chat completions from local LLM."""
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))

        # Build OpenAI-compatible request
        body["stream"] = True
        payload = json.dumps(body).encode()

        parsed = urllib.parse.urlparse(LLM_URL)
        host = parsed.netloc or parsed.path

        try:
            conn = http.client.HTTPConnection(host, timeout=300)
            headers = {"Content-Type": "application/json"}
            # Forward API key if provided (some local servers need it)
            client_key = self.headers.get("X-API-Key")
            if client_key:
                headers["Authorization"] = f"Bearer {client_key}"
            conn.request("POST", "/v1/chat/completions", body=payload, headers=headers)
            resp = conn.getresponse()

            if resp.status != 200:
                data = resp.read()
                self._send(resp.status, "application/json", data)
                conn.close()
                return

            # Stream SSE
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()

            while True:
                line = resp.readline()
                if not line:
                    break
                self.wfile.write(line)
                self.wfile.flush()

            conn.close()
        except Exception as exc:
            try:
                self._send(502, "application/json", json.dumps({"error": str(exc)}).encode())
            except Exception:
                pass

    # ── Helpers ───────────────────────────────────────────────

    def _health(self):
        parsed = urllib.parse.urlparse(LLM_URL)
        llm_host = parsed.netloc or parsed.path
        status = {"stt": False, "tts": False, "llm": False}
        for key, host, path in [
            ("stt", STT_HOST, "/v1/health/ready"),
            ("tts", TTS_HOST, "/v1/health/ready"),
            ("llm", llm_host, "/v1/models"),
        ]:
            try:
                conn = http.client.HTTPConnection(host, timeout=3)
                conn.request("GET", path)
                r = conn.getresponse()
                status[key] = r.status == 200
                conn.close()
            except Exception:
                pass
        self._send(200, "application/json", json.dumps(status).encode())

    def _config(self):
        self._send(200, "application/json", json.dumps({
            "llmUrl": LLM_URL,
        }).encode())

    def _send(self, code, content_type, data):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", len(data))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        if args and str(args[0]).startswith(("4", "5")):
            super().log_message(fmt, *args)


def main():
    here = Path(__file__).parent
    os.chdir(here)

    server = http.server.ThreadingHTTPServer(("", PORT), VoiceChatHandler)

    # Enable HTTPS if cert files exist (required for mic access from remote)
    cert = here / "cert.pem"
    key = here / "key.pem"
    scheme = "http"
    if cert.exists() and key.exists():
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(str(cert), str(key))
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
        scheme = "https"

    import socket
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    print(f"\n  Voice Chat  ->  {scheme}://localhost:{PORT}")
    print(f"                  {scheme}://{local_ip}:{PORT}")
    print(f"  LLM endpoint    {LLM_URL}/v1/chat/completions\n")
    if scheme == "https":
        print("  HTTPS enabled (self-signed cert — accept the browser warning)\n")
    else:
        print("  No cert.pem/key.pem found — running plain HTTP")
        print("  Microphone requires HTTPS on non-localhost. Generate certs with:")
        print("    openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")
        server.server_close()


if __name__ == "__main__":
    main()
