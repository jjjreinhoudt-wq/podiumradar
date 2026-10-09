"""Test voor de Fetcher in sources.py: grootte- en tijdgrens, gewone antwoorden blijven werken (lokale server, geen internet).
Draaien:  python scraper/test_fetch.py"""
import http.server, pathlib, sys, threading
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import sources

class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path == "/robots.txt":
            self.send_response(404); self.end_headers(); return
        body = {"/klein": b"<html><body>hallo</body></html>", "/groot": b"<html>" + b"x" * 5000 + b"</html>", "/json": b'{"a": 1}'}.get(self.path, b"")
        self.send_response(200 if body else 404)
        self.send_header("content-type", "application/json" if self.path == "/json" else "text/html")
        self.send_header("content-length", str(len(body))); self.end_headers(); self.wfile.write(body)

srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_address[1]}"
fouten = 0
def check(naam, kreeg, verwacht):
    global fouten
    ok = kreeg == verwacht; fouten += not ok
    print(f"{'ok  ' if ok else 'FOUT'} {naam}: {kreeg!r}" + ("" if ok else f" (verwacht {verwacht!r})"))

F = sources.Fetcher("test", 0)
check("gewone pagina", "hallo" in (F.get(base + "/klein") or ""), True)
check("json", F.get_json(base + "/json"), {"a": 1})
sources.Fetcher.MAX_BYTES = 1000
check("te grote pagina wordt niet verwerkt", F.get(base + "/groot"), None)
check("... en wordt geteld", F.stats.get("127.0.0.1:" + base.rsplit(":", 1)[1], {}).get("te groot of te traag"), 1)
check("kleine pagina blijft werken na een te grote", "hallo" in (F.get(base + "/klein") or ""), True)
check("404 geeft None", F.get(base + "/bestaat-niet"), None)
srv.shutdown()
print("\n" + ("ALLES GOED" if not fouten else f"{fouten} FOUT(EN)")); sys.exit(1 if fouten else 0)
