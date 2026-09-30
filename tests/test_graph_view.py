import http.client
import threading
from urllib.parse import urlparse

from brainstem.contracts import GraphExportV1, GraphNodeV1
from brainstem.graph_view import start_graph_view


def test_graph_view_is_loopback_token_protected_and_source_free():
    graph = GraphExportV1(root="/repo", nodes=[GraphNodeV1(path="src/app.py", language="python", symbol_count=2)])
    server, url = start_graph_view(graph)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    parsed = urlparse(url)
    try:
        connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=2)
        connection.request("GET", "/api/graph")
        assert connection.getresponse().status == 403

        connection.request("GET", f"/api/graph?{parsed.query}")
        response = connection.getresponse()
        body = response.read().decode("utf-8")
        assert response.status == 200
        assert "src/app.py" in body
        assert "source_text" not in body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
