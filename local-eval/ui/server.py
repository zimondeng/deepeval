"""Minimal local health endpoint for the experimental UI container."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .lifecycle import SubprocessRunner, TaskManager


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/health":
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}\n')

    def log_message(self, format, *args):
        return


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    manager = TaskManager(
        SubprocessRunner(repo_root), "local-eval/compose.yaml"
    )
    manager.cleanup_stale()
    ThreadingHTTPServer(("0.0.0.0", 8787), Handler).serve_forever()


if __name__ == "__main__":
    main()
