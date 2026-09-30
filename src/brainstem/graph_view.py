"""Local-only graph explorer used by ``brainstem graph view``."""

from __future__ import annotations

import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .contracts import GraphExportV1


def start_graph_view(graph: GraphExportV1, port: int = 0) -> tuple[ThreadingHTTPServer, str]:
    """Start a loopback-only graph server and return its secret URL.

    The page receives a structural graph only. It has no route for source
    content, repository files, workflow history, or arbitrary filesystem
    access.
    """
    token = secrets.token_urlsafe(32)
    payload = json.dumps(graph.model_dump(mode="json"), separators=(",", ":"))

    class GraphHandler(BaseHTTPRequestHandler):
        def _authorized(self) -> bool:
            values = parse_qs(urlparse(self.path).query).get("token", [])
            return len(values) == 1 and secrets.compare_digest(values[0], token)

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            parsed = urlparse(self.path)
            if not self._authorized():
                self._send(403, b"Forbidden", "text/plain; charset=utf-8")
            elif parsed.path == "/api/graph":
                self._send(200, payload.encode(), "application/json; charset=utf-8")
            elif parsed.path == "/":
                page = _PAGE.replace("__TOKEN__", token)
                self._send(200, page.encode(), "text/html; charset=utf-8")
            else:
                self._send(404, b"Not found", "text/plain; charset=utf-8")

        def log_message(self, _format: str, *_args: object) -> None:
            # A visualizer should not leak paths through an HTTP access log.
            return

    server = ThreadingHTTPServer(("127.0.0.1", port), GraphHandler)
    url = f"http://127.0.0.1:{server.server_port}/?token={token}"
    return server, url


_PAGE = """<!doctype html><meta charset=utf-8><title>Brainstem graph</title>
<style>body{margin:0;background:#071224;color:#e7eefb;font:14px system-ui,sans-serif}header{padding:20px 28px;border-bottom:1px solid #28415e;background:#0d1d35}h1{margin:0;font-size:20px}.meta{color:#9db1ca;margin-top:5px}main{display:grid;grid-template-columns:300px 1fr;height:calc(100vh - 86px)}aside{padding:18px;overflow:auto;border-right:1px solid #28415e}.node{padding:7px;border-bottom:1px solid #172b44;word-break:break-all}.badge{color:#7be0b1}svg{width:100%;height:100%;background:#09172a}line{stroke:#3c668f;stroke-opacity:.55}circle{fill:#69b7ff;stroke:#c3e4ff;stroke-width:1.5}text{fill:#e7eefb;font-size:11px}</style>
<header><h1>Brainstem repository graph</h1><div class=meta id=meta>Loading local structural data…</div></header><main><aside id=list></aside><svg id=graph aria-label="Repository dependency graph"></svg></main>
<script>fetch('/api/graph?token=__TOKEN__').then(r=>r.json()).then(g=>{const n=g.nodes,e=g.edges,svg=document.querySelector('#graph'),w=svg.clientWidth||900,h=svg.clientHeight||700,cx=w/2,cy=h/2,r=Math.min(w,h)*.36,pos={},ns='http://www.w3.org/2000/svg',add=(name,a,t)=>{let q=document.createElementNS(ns,name);Object.entries(a).forEach(([k,v])=>q.setAttribute(k,String(v)));if(t)q.textContent=t;svg.append(q);return q};n.forEach((x,i)=>{let a=2*Math.PI*i/Math.max(n.length,1);pos[x.path]=[cx+r*Math.cos(a),cy+r*Math.sin(a)]});e.forEach(x=>{if(pos[x.source]&&pos[x.target]){let a=pos[x.source],b=pos[x.target];add('line',{x1:a[0],y1:a[1],x2:b[0],y2:b[1]})}});n.forEach(x=>{let p=pos[x.path],c=add('circle',{cx:p[0],cy:p[1],r:5}),title=document.createElementNS(ns,'title');title.textContent=x.path;c.append(title);add('text',{x:p[0]+8,y:p[1]-8},x.path.split('/').slice(-2).join('/'))});document.querySelector('#meta').textContent=`${n.length} nodes · ${e.length} edges${g.truncated?' · bounded result':''}`;let list=document.querySelector('#list');n.forEach(x=>{let row=document.createElement('div'),name=document.createElement('b'),detail=document.createElement('span');row.className='node';name.textContent=x.path;detail.className='badge';detail.textContent=`${x.language||'unknown'} · ${x.symbol_count} symbols`;row.append(name,document.createElement('br'),detail);list.append(row)})}).catch(()=>document.querySelector('#meta').textContent='Unable to load local graph');</script>"""
