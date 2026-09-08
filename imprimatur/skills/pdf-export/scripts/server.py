"""Local HTTP server for serving HTML files (fixes CDN loading and absolute @font-face paths)."""

import http.server
import socketserver
import threading


def start_http_server(directory: str, port: int = 0):
    """
    Start a local HTTP server for a directory.

    Serve from '/' (filesystem root) to resolve absolute-path @font-face URLs.
    Fonts at /Users/name/fonts/Font.ttf become http://127.0.0.1:PORT/Users/name/fonts/Font.ttf.

    Args:
        directory: Directory to serve (use '/' for filesystem root)
        port: Port to use (0 = pick a free port)

    Returns:
        (httpd, actual_port, base_url)
    """
    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(
        *a, directory=directory, **kw
    )
    httpd = socketserver.TCPServer(("127.0.0.1", port), handler)
    actual_port = httpd.server_address[1]

    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{actual_port}"
    return httpd, actual_port, base_url
