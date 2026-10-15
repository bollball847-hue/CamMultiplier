"""
Built-in plugin: LAN Stream
Shows the copies of the camera in a browser on another device in the same network
(phone, tablet, second PC), e.g.  http://192.168.1.23:8090/?key=ab12cd34
"""
import hmac
import html
import secrets
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import cv2

from cam_multiplier_plugin import Plugin

TEXTS = {
    "en": {
        "port": "Port",
        "quality": "JPEG quality",
        "fps": "Max. frames per second",
        "width": "Max. width (pixels)",
        "key": "Access key",
        "new_key": "New key",
        "url": "Link",
        "copy": "Copy link",
        "save": "Save",
        "title": "LAN Stream",
        "warning": ("Anyone in your network who has this link can watch the picture. The stream is not "
                    "encrypted - use it only in networks you trust. Windows may ask to allow network access "
                    "the first time: choose private networks."),
        "running": "LAN stream: {url}",
        "port_busy": "LAN stream could not start: port {port} is already in use.",
        "invalid": "Please enter valid numbers.",
    },
    "de": {
        "port": "Port",
        "quality": "JPEG-Qualität",
        "fps": "Max. Bilder pro Sekunde",
        "width": "Max. Breite (Pixel)",
        "key": "Zugangsschlüssel",
        "new_key": "Neuer Schlüssel",
        "url": "Link",
        "copy": "Link kopieren",
        "save": "Speichern",
        "title": "LAN-Stream",
        "warning": ("Jeder in deinem Netzwerk, der diesen Link hat, kann das Bild ansehen. Der Stream ist nicht "
                    "verschlüsselt - nur in Netzwerken nutzen, denen du vertraust. Windows fragt beim ersten Mal "
                    "evtl. nach Netzwerkzugriff: private Netzwerke erlauben."),
        "running": "LAN-Stream: {url}",
        "port_busy": "LAN-Stream konnte nicht starten: Port {port} wird bereits benutzt.",
        "invalid": "Bitte gültige Zahlen eingeben.",
    },
}


def local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # no packet is sent, this only picks the right interface
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def new_key():
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    return "".join(secrets.choice(alphabet) for _ in range(8))


class _Handler(BaseHTTPRequestHandler):
    plugin = None  # set per server

    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype="text/plain; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        p = self.plugin
        u = urlparse(self.path)
        q = parse_qs(u.query)
        key = q.get("key", [""])[0]
        if not hmac.compare_digest(key.encode("utf-8"), p.key.encode("utf-8")):
            self._send(401, "Access key required")
            return
        try:
            copy = max(1, int(q.get("copy", ["1"])[0])) - 1
        except ValueError:
            copy = 0
        try:
            if u.path in ("", "/"):
                self._page(copy, key)
            elif u.path == "/stream":
                self._stream(copy)
            elif u.path == "/snapshot.jpg":
                jpg, _ = p.jpeg(copy, 0)
                if jpg is None:
                    self._send(503, "No picture yet")
                else:
                    self._send(200, jpg, "image/jpeg")
            else:
                self._send(404, "Not found")
        except (BrokenPipeError, ConnectionError, OSError):
            pass

    def _page(self, copy, key):
        p = self.plugin
        k = html.escape(key)
        links = " ".join(
            f'<a href="/?copy={i + 1}&key={k}">{i + 1}</a>' for i in range(max(1, p.copies)))
        page = (
            "<!doctype html><html><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            "<title>Cam Multiplier</title><style>"
            "body{margin:0;background:#000;color:#9ab;font:14px sans-serif;text-align:center}"
            "img{max-width:100%;max-height:92vh;display:block;margin:auto}"
            "a{color:#21b6ff;margin:0 8px;text-decoration:none}</style></head><body>"
            f"<img src='/stream?copy={copy + 1}&key={k}' alt=''>"
            f"<p>{links}</p></body></html>")
        self._send(200, page, "text/html; charset=utf-8")

    def _stream(self, copy):
        p = self.plugin
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        last = 0
        while p.running:
            t0 = time.time()
            jpg, fid = p.jpeg(copy, last)
            if jpg is None:
                time.sleep(0.02)
                continue
            last = fid
            self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(jpg))
            self.wfile.write(jpg)
            self.wfile.write(b"\r\n")
            wait = 1.0 / p.fps - (time.time() - t0)
            if wait > 0:
                time.sleep(wait)


class LanStream(Plugin):
    id = "lan_stream"
    name = {"en": "LAN Stream", "de": "LAN-Stream"}
    description = {
        "en": "Watch the copies in a browser on another device in the same Wi-Fi or network.",
        "de": "Die Kopien im Browser eines anderen Geräts im selben WLAN oder Netzwerk ansehen.",
    }
    version = "1.0"
    priority = 100  # runs after effect plugins, so the stream shows the final picture

    def __init__(self, api):
        super().__init__(api)
        self.server = None
        self.thread = None
        self.running = False
        self.frames = {}
        self.counters = {}
        self.jpeg_cache = {}
        self.lock = threading.Lock()
        self.copies = 1
        if not api.get_setting("key"):
            api.set_setting("key", new_key())
        self._load()

    def tr(self, key, **kw):
        s = TEXTS.get(self.api.lang, TEXTS["en"]).get(key) or TEXTS["en"][key]
        return s.format(**kw) if kw else s

    def _load(self):
        g = self.api.get_setting
        self.port = int(g("port", 8090))
        self.quality = int(g("quality", 80))
        self.fps = max(1, int(g("fps", 20)))
        self.max_width = int(g("max_width", 1280))
        self.key = str(g("key"))

    def url(self):
        return f"http://{local_ip()}:{self.port}/?key={self.key}"

    # ---- plugin hooks
    def on_start(self, info):
        self._load()
        self.copies = int(info.get("copies", 1))
        self.frames, self.counters, self.jpeg_cache = {}, {}, {}
        handler = type("LanHandler", (_Handler,), {"plugin": self})
        try:
            self.server = ThreadingHTTPServer(("0.0.0.0", self.port), handler)
        except OSError:
            self.server = None
            self.api.log(f"port {self.port} is in use")
            self.api.set_info(self.tr("port_busy", port=self.port))
            return
        self.server.daemon_threads = True
        self.running = True
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={"poll_interval": 0.2}, daemon=True)
        self.thread.start()
        self.api.set_info(self.tr("running", url=self.url()))

    def on_frame(self, copy_index, frame):
        if self.server is not None:
            n = self.counters.get(copy_index, 0) + 1
            self.counters[copy_index] = n
            self.frames[copy_index] = (n, frame)
        return None

    def on_stop(self):
        self.running = False
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        self.api.set_info(None)

    # ---- JPEG encoding, shared between all viewers
    def jpeg(self, copy, last_id):
        entry = self.frames.get(copy)
        if entry is None or entry[0] == last_id:
            return None, last_id
        fid, frame = entry
        with self.lock:
            cached = self.jpeg_cache.get(copy)
            if cached and cached[0] == fid:
                return cached[1], fid
            img = frame
            if self.max_width and img.shape[1] > self.max_width:
                h = int(img.shape[0] * self.max_width / img.shape[1])
                img = cv2.resize(img, (self.max_width, h))
            ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, self.quality])
            if not ok:
                return None, last_id
            data = buf.tobytes()
            self.jpeg_cache[copy] = (fid, data)
            return data, fid

    # ---- settings window
    def settings_ui(self, parent):
        import tkinter as tk
        from tkinter import ttk

        parent.title(self.tr("title"))
        parent.resizable(False, False)
        pad = {"padx": 10, "pady": 5}
        port = tk.StringVar(value=str(self.port))
        quality = tk.StringVar(value=str(self.quality))
        fps = tk.StringVar(value=str(self.fps))
        width = tk.StringVar(value=str(self.max_width))
        key = tk.StringVar(value=self.key)
        url = tk.StringVar()

        def refresh_url(*_):
            url.set(f"http://{local_ip()}:{port.get().strip() or '?'}/?key={key.get().strip()}")

        rows = [("port", ttk.Spinbox(parent, from_=1024, to=65535, textvariable=port, width=8)),
                ("quality", ttk.Spinbox(parent, from_=30, to=95, textvariable=quality, width=8)),
                ("fps", ttk.Spinbox(parent, from_=1, to=30, textvariable=fps, width=8)),
                ("width", ttk.Combobox(parent, values=["640", "960", "1280", "1920"],
                                       textvariable=width, width=8))]
        for r, (label, widget) in enumerate(rows):
            ttk.Label(parent, text=self.tr(label)).grid(row=r, column=0, sticky="w", **pad)
            widget.grid(row=r, column=1, sticky="w", **pad)

        ttk.Label(parent, text=self.tr("key")).grid(row=4, column=0, sticky="w", **pad)
        kf = ttk.Frame(parent)
        kf.grid(row=4, column=1, sticky="w", **pad)
        ttk.Entry(kf, textvariable=key, width=14).pack(side="left")
        ttk.Button(kf, text=self.tr("new_key"), command=lambda: key.set(new_key())).pack(side="left", padx=6)

        ttk.Label(parent, text=self.tr("url")).grid(row=5, column=0, sticky="w", **pad)
        uf = ttk.Frame(parent)
        uf.grid(row=5, column=1, sticky="w", **pad)
        ttk.Entry(uf, textvariable=url, width=38, state="readonly").pack(side="left")

        def copy_url():
            parent.clipboard_clear()
            parent.clipboard_append(url.get())

        ttk.Button(uf, text=self.tr("copy"), command=copy_url).pack(side="left", padx=6)
        for v in (port, key):
            v.trace_add("write", refresh_url)
        refresh_url()

        ttk.Label(parent, text=self.tr("warning"), wraplength=480, justify="left")\
            .grid(row=6, column=0, columnspan=2, sticky="w", **pad)

        def save():
            try:
                values = dict(port=int(port.get()), quality=int(quality.get()),
                              fps=int(fps.get()), max_width=int(width.get()))
                if not (1024 <= values["port"] <= 65535 and 30 <= values["quality"] <= 95
                        and 1 <= values["fps"] <= 30 and values["max_width"] >= 160 and key.get().strip()):
                    raise ValueError
            except ValueError:
                from tkinter import messagebox
                messagebox.showerror(self.tr("title"), self.tr("invalid"), parent=parent)
                return
            for k, v in values.items():
                self.api.set_setting(k, v)
            self.api.set_setting("key", "".join(c for c in key.get().strip() if c.isalnum()))
            self._load()
            parent.destroy()

        ttk.Button(parent, text=self.tr("save"), command=save).grid(row=7, column=0, columnspan=2, pady=10)
