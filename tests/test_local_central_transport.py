import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from src.service.local_central_transport import proxy_request


def test_proxy_request_does_not_follow_central_redirects_to_an_external_page():
    class RedirectHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/start":
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/external")
                self.end_headers()
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"external-page")

        def log_message(self, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        status, headers, body = proxy_request(
            f"http://127.0.0.1:{server.server_port}",
            "GET",
            "/start",
        )
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)

    assert status == 302
    assert headers["Location"].endswith("/external")
    assert body == b""
