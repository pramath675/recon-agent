"""Tiny local OpenAI-compatible server for testing RECON's HTTP path WITHOUT Nebius or credits.
Usage: python tests/mock_server.py 8765 examples/fixtures/good
Replies to the 1st request with the repro test and the 2nd with the patch."""
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

port, fx = int(sys.argv[1]), Path(sys.argv[2])
replies = [json.dumps({"explanation": "mock", "test_code": (fx / "repro_test.txt").read_text()}),
           (fx / "patch.json").read_text()]
seen = {"n": 0}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert self.headers["Authorization"] == "Bearer mock-key" and self.path.endswith("/chat/completions")
        content = replies[min(seen["n"], len(replies) - 1)]
        seen["n"] += 1
        out = json.dumps({"choices": [{"message": {"content": content}, "finish_reason": "stop"}],
                          "usage": {"prompt_tokens": 1234, "completion_tokens": 321}}).encode()
        print(f"[mock] request {seen['n']} model={body['model']} max_tokens={body['max_tokens']}", flush=True)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


HTTPServer(("127.0.0.1", port), Handler).serve_forever()
