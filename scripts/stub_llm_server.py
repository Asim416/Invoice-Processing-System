"""Local STUB of an OpenAI-compatible /v1/chat/completions endpoint. NOT a real LLM.

It looks up the ground-truth JSON for the invoice it is sent (matching on the invoice number) so the real
OpenAI-SDK request path, retry logic and parsing can be exercised offline. Used for development and fault tests.

  python scripts/stub_llm_server.py --port 8765 [--fail-first 2 --fail-status 429] [--garbage]
"""
import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRUTH = {json.loads(p.read_text())["invoice_number"]: p.read_text()
         for p in (ROOT / "data" / "ground_truth").glob("*.json")}
STATE = {"calls": 0, "last_request": None}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):  # /stats for tests
        self.send_response(200); self.end_headers()
        self.wfile.write(json.dumps({"calls": STATE["calls"], "last_request": STATE["last_request"]}).encode())

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        STATE["calls"] += 1
        STATE["last_request"] = {"path": self.path, "auth": self.headers.get("Authorization", "")[:12] + "...",
                                 "model": body.get("model"), "temperature": body.get("temperature"),
                                 "response_format_type": body.get("response_format", {}).get("type"),
                                 "strict": body.get("response_format", {}).get("json_schema", {}).get("strict"),
                                 "has_system_prompt": body["messages"][0]["role"] == "system"}
        if STATE["calls"] <= ARGS.fail_first:
            self.send_response(ARGS.fail_status); self.send_header("retry-after", "0")
            self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(b'{"error": {"message": "stub failure"}}'); return
        user = body["messages"][-1]["content"]
        content = "{garbage" if ARGS.garbage else next((t for n, t in TRUTH.items() if f"{n}" in user), "{}")
        out = {"id": "stub", "object": "chat.completion", "model": body.get("model"),
               "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
               "usage": {"prompt_tokens": 700, "completion_tokens": 220, "total_tokens": 920}}
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps(out).encode())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--fail-first", type=int, default=0)
    ap.add_argument("--fail-status", type=int, default=429)
    ap.add_argument("--garbage", action="store_true")
    ARGS = ap.parse_args()
    print(f"stub LLM server on 127.0.0.1:{ARGS.port} (NOT a real model)", file=sys.stderr)
    HTTPServer(("127.0.0.1", ARGS.port), Handler).serve_forever()
