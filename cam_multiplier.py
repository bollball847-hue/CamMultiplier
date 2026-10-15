"""
Cam Multiplier
One webcam (or a network stream), several virtual cameras. For OBS, Discord, Teams and more.
Requires the Unity Capture driver (bundled with the installer).
"""
import ctypes
import faulthandler
import json
import logging
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
from urllib.parse import urlparse, urlunparse

import cv2
from PIL import Image, ImageTk

from cam_multiplier_plugin import PluginManager, localized
from plugin_lan_stream import LanStream
from unitycapture_sender import VirtualCamera, capnum_from_name

try:
    from pygrabber.dshow_graph import FilterGraph
except Exception:
    FilterGraph = None

# network streams: give up on a dead connection after 5 seconds instead of ~30
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rw_timeout;5000000|stimeout;5000000")

APP_NAME = "Cam Multiplier"
DEFAULT_BASE = "Cam Multiplier"
MAX_COPIES = 10
RECONNECT_AFTER = 3.0  # seconds without a frame before the source is reopened
RESOLUTIONS = {"1280 x 720": (1280, 720), "1920 x 1080": (1920, 1080)}
SIZE_KEYS = ["same"] + list(RESOLUTIONS)  # per-copy output size: "same" = as the source
CAPTURE_FPS_CHOICES = [15, 24, 30, 60]
OUT_FPS_CHOICES = [10, 15, 20, 24, 30]
ROTATIONS = [0, 90, 180, 270]
DEFAULT_COPY = {"mirror": False, "size": "same", "fps": 0, "zoom": 100,
                "rotate": 0, "brightness": 0, "contrast": 100}


# ----------------------------------------------------------------- languages
# To add a language: copy the "en" block, translate the values, and add the
# language to LANG_NAMES. Missing keys fall back to English.
LANG_NAMES = {"en": "English", "de": "Deutsch"}

STRINGS = {
    "en": {
        "camera": "Camera",
        "source_link": "Stream from link ...",
        "link": "Link",
        "link_hint": "Paste the link shown by LAN Stream on another PC, or any http/rtsp video stream.",
        "copies": "Number of copies",
        "settings": "Settings",
        "cam_settings_title": "Camera settings",
        "resolution": "Camera resolution",
        "capture_fps": "Camera frame rate",
        "copy_n": "Copy {n}",
        "copy_settings_title": "Copy {n} settings",
        "name": "Name",
        "soon": "Coming soon",
        "dev_note": "This and more features are in development.",
        "fps": "Output frame rate",
        "zoom": "Zoom (%)",
        "rotate": "Rotation",
        "brightness": "Brightness",
        "contrast": "Contrast (%)",
        "reset": "Reset",
        "ok": "OK",
        "restart_needed": "Output size and rotation change with the next Start.",
        "mirror": "Mirror",
        "size": "Size",
        "size_same": "Same as source",
        "start": "Start",
        "stop": "Stop",
        "setup": "Set up cameras",
        "language": "Language",
        "plugins": "Plugins",
        "plugins_title": "Plugins",
        "plugins_note": "Plugins add extra features. Changes apply the next time you press Start.",
        "plugin_settings": "Settings",
        "plugin_no_settings": "This plugin has no settings.",
        "plugin_external": "external",
        "plugins_folder": "Open plugin folder",
        "plugins_close": "Close",
        "plugins_warn_title": "Enable plugin?",
        "plugins_warn_msg": "'{name}' is an external plugin. Plugins run code on your PC with the same rights as this program. Only enable plugins from sources you trust.",
        "plugin_failed": "Plugin '{name}' was switched off after repeated errors (see app.log).",
        "plugin_load_failed": "Plugin '{name}' could not be loaded (see app.log).",
        "status_ready": "Ready.",
        "status_opening": "Opening source ...",
        "status_need_link": "Enter a link first.",
        "status_no_frame": "No image from the camera. Close OBS and other camera apps, then try again.",
        "status_no_stream": "Could not read the stream. Check the link and make sure the other device is streaming.",
        "status_not_enough": "Only {found} virtual camera(s) installed, {wanted} requested. Use 'Set up cameras' to change this.",
        "status_running": "Running: {names}",
        "status_reconnecting": "Connection lost - reconnecting ...",
        "status_stopped": "Stopped.",
        "status_no_vcams": "No virtual cameras installed. Click 'Set up cameras'.",
        "status_waiting_admin": "Setting up cameras - please confirm the Windows prompt ...",
        "setup_title": "Set up cameras",
        "setup_name": "Name (a number is appended automatically)",
        "setup_count": "Number of virtual cameras (1-10)",
        "setup_note": "Close OBS and other programs that use the cameras first.\nWindows will ask for administrator permission.",
        "setup_apply": "Apply",
        "err_title": "Error",
        "err_driver_missing": "Driver files are missing (folder 'driver').",
        "err_admin": "Cancelled, or no administrator rights.",
        "err_register": "Registering the cameras failed. Run the setup again or reinstall the program.",
        "err_generic": "Error: {err}",
        "restart_title": "Done",
        "restart_msg": "The cameras were set up. The program will restart now.",
    },
    "de": {
        "camera": "Kamera",
        "source_link": "Stream von Link ...",
        "link": "Link",
        "link_hint": "Link einfügen, den der LAN-Stream auf einem anderen PC anzeigt, oder einen beliebigen http-/rtsp-Videostream.",
        "copies": "Anzahl Kopien",
        "settings": "Einstellungen",
        "cam_settings_title": "Kamera-Einstellungen",
        "resolution": "Kameraauflösung",
        "capture_fps": "Kamera-Bildrate",
        "copy_n": "Kopie {n}",
        "copy_settings_title": "Einstellungen für Kopie {n}",
        "name": "Name",
        "soon": "Demnächst",
        "dev_note": "Diese und weitere Funktionen sind in Entwicklung.",
        "fps": "Ausgabe-Bildrate",
        "zoom": "Zoom (%)",
        "rotate": "Drehung",
        "brightness": "Helligkeit",
        "contrast": "Kontrast (%)",
        "reset": "Zurücksetzen",
        "ok": "OK",
        "restart_needed": "Ausgabegröße und Drehung gelten ab dem nächsten Start.",
        "mirror": "Spiegeln",
        "size": "Größe",
        "size_same": "Wie Quelle",
        "start": "Start",
        "stop": "Stopp",
        "setup": "Kameras einrichten",
        "language": "Sprache",
        "plugins": "Plugins",
        "plugins_title": "Plugins",
        "plugins_note": "Plugins fügen zusätzliche Funktionen hinzu. Änderungen gelten beim nächsten Start.",
        "plugin_settings": "Einstellungen",
        "plugin_no_settings": "Dieses Plugin hat keine Einstellungen.",
        "plugin_external": "extern",
        "plugins_folder": "Plugin-Ordner öffnen",
        "plugins_close": "Schließen",
        "plugins_warn_title": "Plugin aktivieren?",
        "plugins_warn_msg": "'{name}' ist ein externes Plugin. Plugins führen Code auf deinem PC mit denselben Rechten wie dieses Programm aus. Aktiviere nur Plugins aus Quellen, denen du vertraust.",
        "plugin_failed": "Plugin '{name}' wurde nach wiederholten Fehlern abgeschaltet (siehe app.log).",
        "plugin_load_failed": "Plugin '{name}' konnte nicht geladen werden (siehe app.log).",
        "status_ready": "Bereit.",
        "status_opening": "Quelle wird geöffnet ...",
        "status_need_link": "Bitte zuerst einen Link eintragen.",
        "status_no_frame": "Kein Bild von der Kamera. OBS und andere Kamera-Programme schließen und erneut versuchen.",
        "status_no_stream": "Der Stream konnte nicht gelesen werden. Link prüfen und sicherstellen, dass das andere Gerät streamt.",
        "status_not_enough": "Nur {found} virtuelle Kamera(s) installiert, {wanted} gewünscht. Über 'Kameras einrichten' ändern.",
        "status_running": "Läuft: {names}",
        "status_reconnecting": "Verbindung verloren - verbinde neu ...",
        "status_stopped": "Gestoppt.",
        "status_no_vcams": "Keine virtuellen Kameras installiert. 'Kameras einrichten' klicken.",
        "status_waiting_admin": "Kameras werden eingerichtet - bitte die Windows-Rückfrage bestätigen ...",
        "setup_title": "Kameras einrichten",
        "setup_name": "Name (Nummer wird automatisch angehängt)",
        "setup_count": "Anzahl virtueller Kameras (1-10)",
        "setup_note": "OBS und andere Programme, die die Kameras nutzen, vorher schließen.\nWindows fragt nach Administratorrechten.",
        "setup_apply": "Übernehmen",
        "err_title": "Fehler",
        "err_driver_missing": "Treiberdateien fehlen (Ordner 'driver').",
        "err_admin": "Abgebrochen oder keine Administratorrechte.",
        "err_register": "Das Einrichten der Kameras ist fehlgeschlagen. Erneut versuchen oder das Programm neu installieren.",
        "err_generic": "Fehler: {err}",
        "restart_title": "Fertig",
        "restart_msg": "Die Kameras wurden eingerichtet. Das Programm wird jetzt neu gestartet.",
    },
}

_lang = "en"


def detect_language():
    """English by default, German if Windows itself is set to German."""
    try:
        langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        if (langid & 0x3FF) == 0x07:
            return "de"
    except Exception:
        pass
    return "en"


def t(key, **kw):
    s = STRINGS.get(_lang, {}).get(key) or STRINGS["en"].get(key, key)
    return s.format(**kw) if kw else s


def size_labels():
    return [t("size_same")] + list(RESOLUTIONS)


def size_value(key):
    return None if key == "same" else RESOLUTIONS[key]


# ------------------------------------------------------------------ settings
def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(name):
    """Bundled files (icon): next to the script, or inside the PyInstaller bundle."""
    base = getattr(sys, "_MEIPASS", app_dir())
    return os.path.join(base, "assets", name)


DATA_DIR = os.path.join(os.environ.get("APPDATA", app_dir()), "CamMultiplier")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
PLUGIN_DIR = os.path.join(DATA_DIR, "plugins")
PLUGIN_DATA_DIR = os.path.join(DATA_DIR, "plugin_data")
_crash_file = None


def setup_logging():
    """Writes app.log and crash.log into %APPDATA%\\CamMultiplier (helps to find bugs)."""
    global _crash_file
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        logging.basicConfig(filename=os.path.join(DATA_DIR, "app.log"), level=logging.INFO,
                            format="%(asctime)s %(levelname)s %(message)s")
        _crash_file = open(os.path.join(DATA_DIR, "crash.log"), "a")
        faulthandler.enable(file=_crash_file, all_threads=True)
    except Exception:
        pass
    sys.excepthook = lambda tp, v, tb: logging.error("Uncaught error", exc_info=(tp, v, tb))
    threading.excepthook = lambda a: logging.error(
        "Thread error", exc_info=(a.exc_type, a.exc_value, a.exc_traceback))


def load_settings():
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(data):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass


def _num(value, default, low, high):
    try:
        return max(low, min(high, int(float(value))))
    except (TypeError, ValueError):
        return default


def clean_copy(o):
    """Returns a complete, valid option dict for one copy (also used for old settings files)."""
    o = o if isinstance(o, dict) else {}
    c = dict(DEFAULT_COPY)
    c["mirror"] = bool(o.get("mirror", c["mirror"]))
    c["size"] = o.get("size") if o.get("size") in SIZE_KEYS else "same"
    c["fps"] = _num(o.get("fps"), 0, 0, 60)
    c["zoom"] = _num(o.get("zoom"), 100, 100, 400)
    c["rotate"] = o.get("rotate") if o.get("rotate") in ROTATIONS else 0
    c["brightness"] = _num(o.get("brightness"), 0, -100, 100)
    c["contrast"] = _num(o.get("contrast"), 100, 50, 200)
    return c


# ------------------------------------------------------------------- devices
_graph = None


def all_devices():
    """DirectShow video devices, in the same order OpenCV (CAP_DSHOW) uses."""
    global _graph
    if FilterGraph is None:
        return []
    try:
        if _graph is None:
            _graph = FilterGraph()
        return list(_graph.get_input_devices())
    except Exception:
        logging.exception("Device enumeration failed")
        _graph = None
        return []


def is_virtual(name, base):
    n = name.lower()
    return n.startswith(base.lower()) or n.startswith("unity video capture")


# ------------------------------------------------------------------- sources
ALL_MODES = [(be, mjpg, size)
             for be in (cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY)
             for mjpg in (False, True)
             for size in (True, False)]


def normalize_stream_url(text):
    """Accepts the link shown by LAN Stream (page link) and turns it into the video link."""
    text = (text or "").strip()
    if not text:
        return ""
    if "://" not in text:
        text = "http://" + text
    u = urlparse(text)
    if u.scheme in ("http", "https") and u.path in ("", "/"):
        u = u._replace(path="/stream")
    return urlunparse(u)


def open_camera(index, width, height, fps, stop=None, modes=None, tries=20):
    """Tries backends and modes until a real image arrives.
    Returns (capture, mode, first_frame) or (None, None, None). 'stop' is a threading.Event."""
    for mode in (modes or ALL_MODES):
        if stop is not None and stop.is_set():
            return None, None, None
        be, mjpg, size = mode
        cap = cv2.VideoCapture(index, be)
        if not cap.isOpened():
            cap.release()
            continue
        if mjpg:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        if size:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            cap.set(cv2.CAP_PROP_FPS, fps)
        for _ in range(tries):
            if stop is not None and stop.is_set():
                cap.release()
                return None, None, None
            ok, frame = cap.read()
            if ok and frame is not None and frame.mean() > 1:
                return cap, mode, frame
            time.sleep(0.1)
        cap.release()
    return None, None, None


def open_stream(url, stop=None, tries=20):
    """Opens a network video stream (http MJPEG, rtsp, ...)."""
    if stop is not None and stop.is_set():
        return None, None, None
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        cap.release()
        return None, None, None
    for _ in range(tries):
        if stop is not None and stop.is_set():
            break
        ok, frame = cap.read()
        if ok and frame is not None:
            return cap, ("stream",), frame
        time.sleep(0.1)
    cap.release()
    return None, None, None


def open_source(source, width, height, fps, stop=None, modes=None, tries=20):
    if isinstance(source, str):
        return open_stream(source, stop, tries)
    return open_camera(source, width, height, fps, stop, modes, tries)


def apply_options(frame, o, out_w, out_h):
    """Zoom -> rotate -> mirror -> brightness/contrast -> scale to the output size."""
    img = frame
    zoom = o.get("zoom", 100)
    if zoom > 100:
        h, w = img.shape[:2]
        cw, ch = max(2, int(w * 100 / zoom)), max(2, int(h * 100 / zoom))
        x0, y0 = (w - cw) // 2, (h - ch) // 2
        img = img[y0:y0 + ch, x0:x0 + cw]
    rot = o.get("rotate", 0)
    if rot == 90:
        img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    elif rot == 180:
        img = cv2.rotate(img, cv2.ROTATE_180)
    elif rot == 270:
        img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    if o.get("mirror"):
        img = cv2.flip(img, 1)
    brightness, contrast = o.get("brightness", 0), o.get("contrast", 100)
    if brightness or contrast != 100:
        img = cv2.convertScaleAbs(img, alpha=contrast / 100.0, beta=brightness)
    if img.shape[1] != out_w or img.shape[0] != out_h:
        img = cv2.resize(img, (out_w, out_h))
    return img


def install_driver(base, count):
    """(Re-)registers the virtual cameras. Needs administrator rights.
    Returns None on success or (message_key, format_args) on failure."""
    d = os.path.join(app_dir(), "driver")
    dll64 = os.path.join(d, "UnityCaptureFilter64.dll")
    dll32 = os.path.join(d, "UnityCaptureFilter32.dll")
    if not (os.path.exists(dll64) and os.path.exists(dll32)):
        return ("err_driver_missing", {})
    win = os.environ.get("WINDIR", r"C:\Windows")
    r64 = os.path.join(win, "System32", "regsvr32.exe")
    r32 = os.path.join(win, "SysWOW64", "regsvr32.exe")
    errfile = os.path.join(tempfile.gettempdir(), "cam_multiplier_setup.err")
    try:
        os.remove(errfile)
    except OSError:
        pass
    args = f'"/i:UnityCaptureDevices={count}" "/i:UnityCaptureName={base}"'
    lines = [
        "@echo off",
        f'"{r64}" /s /u "{dll64}"',
        f'"{r32}" /s /u "{dll32}"',
        f'"{r64}" /s "{dll64}" {args}',
        f'if errorlevel 1 echo fail> "{errfile}"',
        f'"{r32}" /s "{dll32}" {args}',
        f'if errorlevel 1 echo fail> "{errfile}"',
    ]
    bat = os.path.join(tempfile.gettempdir(), "cam_multiplier_setup.bat")
    try:
        with open(bat, "w", encoding="utf-8") as f:
            f.write("\r\n".join(lines) + "\r\n")
        ps = ("Start-Process -FilePath '%s' -Verb RunAs -Wait -WindowStyle Hidden"
              % bat.replace("'", "''"))
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           stdin=subprocess.DEVNULL, capture_output=True, text=True,
                           timeout=180, creationflags=0x08000000)  # CREATE_NO_WINDOW
    except Exception as e:
        logging.exception("install_driver failed")
        return ("err_generic", {"err": str(e)})
    if r.returncode != 0:
        return ("err_admin", {})
    if os.path.exists(errfile):
        return ("err_register", {})
    return None


# -------------------------------------------------------------------- worker
class Worker:
    def __init__(self):
        self.running = False
        self.thread = None
        self.stop_event = None
        self.latest = None
        self.status = ("status_ready", {})

    def start(self, **opts):
        self.stop()
        ev = threading.Event()
        self.stop_event = ev
        self.running = True
        self.thread = threading.Thread(target=self._run, args=(ev,), kwargs=opts, daemon=True)
        self.thread.start()

    def stop(self):
        if self.stop_event is not None:
            self.stop_event.set()
        self.running = False
        if self.thread:
            self.thread.join(timeout=3)
        self.thread = None
        self.latest = None

    def _set(self, ev, key, **kw):
        if not ev.is_set():
            self.status = (key, kw)

    def _run(self, ev, **opts):
        try:
            self._loop(ev, **opts)
        except Exception as e:
            logging.exception("Worker crashed")
            self._set(ev, "err_generic", err=str(e))
        finally:
            if self.stop_event is ev:
                self.running = False

    def _loop(self, ev, source, copies, size, fps, copy_opts, vdevs, plugins=None):
        is_stream = isinstance(source, str)
        self._set(ev, "status_opening")
        cap, mode, first = open_source(source, size[0], size[1], fps, stop=ev)
        if cap is None:
            self._set(ev, "status_no_stream" if is_stream else "status_no_frame")
            return
        src_h, src_w = first.shape[:2]
        if len(vdevs) < copies:
            cap.release()
            self._set(ev, "status_not_enough", found=len(vdevs), wanted=copies)
            return
        outs = []
        for o in copy_opts[:copies]:
            out = size_value(o["size"])
            if out is None:
                out = (src_h, src_w) if o["rotate"] in (90, 270) else (src_w, src_h)
            outs.append(out)
        cams = [VirtualCamera(num) for num, _name in vdevs[:copies]]
        running = ("status_running", {"names": ", ".join(n for _, n in vdevs[:copies])})
        self._set(ev, running[0], **running[1])

        hooks = False
        if plugins is not None:
            plugins.start_all({"copies": copies, "names": [n for _, n in vdevs[:copies]],
                               "sizes": [list(o) for o in outs], "fps": fps})
            hooks = plugins.has_frame_hooks()

        period = 1.0 / fps
        next_tick = time.time()
        next_send = [0.0] * copies
        last_ok = time.time()
        last_try = 0.0
        last_rgbas = None
        pending = first  # the picture that was read while opening
        try:
            while not ev.is_set():
                frame = None
                now = time.time()
                if pending is not None:
                    frame, pending, last_ok = pending, None, now
                elif cap is not None:
                    ok, f = cap.read()
                    if ok and f is not None:
                        frame = f
                        last_ok = time.time()
                    elif now - last_ok > RECONNECT_AFTER:
                        # Source vanished (unplugged, stream stopped): keep the virtual cameras
                        # alive with the last picture and try to reopen the source.
                        cap.release()
                        cap = None
                        last_try = 0.0
                        self._set(ev, "status_reconnecting")
                        logging.warning("Connection lost, reconnecting")
                elif now - last_try > 2.0:
                    last_try = now
                    cap, _m, frame = open_source(source, size[0], size[1], fps, stop=ev,
                                                 modes=[mode] if not is_stream else None, tries=10)
                    if cap is not None:
                        last_ok = time.time()
                        self._set(ev, running[0], **running[1])
                        logging.info("Source reconnected")

                if frame is not None:
                    cache = {}
                    rgbas = []
                    first_img = None
                    for i, (ow, oh) in enumerate(outs):
                        o = copy_opts[i]
                        key = (bool(o.get("mirror")), o.get("zoom", 100), o.get("rotate", 0),
                               o.get("brightness", 0), o.get("contrast", 100), ow, oh)
                        if key not in cache:
                            img = apply_options(frame, o, ow, oh)
                            cache[key] = (img, cv2.cvtColor(img, cv2.COLOR_BGR2RGBA))
                        img, rgba = cache[key]
                        if hooks:
                            # the picture is shared between copies, so plugins get it read-only
                            img.setflags(write=False)
                            out = plugins.on_frame(i, img)
                            if out is not img:
                                img, rgba = out, cv2.cvtColor(out, cv2.COLOR_BGR2RGBA)
                        if first_img is None:
                            first_img = img
                        rgbas.append(rgba)
                    self.latest = first_img
                    last_rgbas = rgbas

                if last_rgbas is not None:
                    t_now = time.time()
                    for i, cam in enumerate(cams):
                        out_fps = copy_opts[i].get("fps", 0)
                        if out_fps and t_now < next_send[i]:
                            continue
                        next_send[i] = t_now + (1.0 / out_fps if out_fps else 0.0)
                        cam.send(last_rgbas[i])
                next_tick += period
                delay = next_tick - time.time()
                if delay > 0:
                    time.sleep(delay)
                else:
                    next_tick = time.time()
        finally:
            if plugins is not None:
                plugins.stop_all()
            for c in cams:
                c.close()
            if cap is not None:
                cap.release()


# ------------------------------------------------------------------------ UI
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        global _lang
        self.resizable(False, False)
        try:
            self.iconbitmap(default=resource_path("icon.ico"))
        except Exception:
            logging.warning("Could not load the window icon")
        self.worker = Worker()
        self.cfg = load_settings()
        _lang = self.cfg.get("lang") or detect_language()
        self.plugins = PluginManager(cfg=self.cfg, save=lambda: save_settings(self.cfg),
                                     lang=lambda: _lang, plugin_dir=PLUGIN_DIR,
                                     data_dir=PLUGIN_DATA_DIR, builtin=[LanStream])
        self.base = self.cfg.get("base", DEFAULT_BASE)
        self.real = []
        self.vnames = []
        self.ui_running = False
        self.events = queue.Queue()  # lets background threads talk to the UI safely

        # settings of every copy (the worker reads these dicts directly, so most changes are live)
        saved = self.cfg.get("copy_opts", [])
        old_mirror = bool(self.cfg.get("mirror", False))  # setting from version 1.0
        self.copy_cfg = []
        for i in range(MAX_COPIES):
            o = saved[i] if i < len(saved) and isinstance(saved[i], dict) else {"mirror": old_mirror}
            self.copy_cfg.append(clean_copy(o))
        self.capture_res = self.cfg.get("res") if self.cfg.get("res") in RESOLUTIONS else "1280 x 720"
        self.capture_fps = _num(self.cfg.get("capture_fps"), 30, 5, 60)

        pad = {"padx": 10, "pady": 5}
        self.lbl_cam = ttk.Label(self)
        self.lbl_cam.grid(row=0, column=0, sticky="w", **pad)
        self.cam_box = ttk.Combobox(self, state="readonly", width=38)
        self.cam_box.grid(row=0, column=1, sticky="w", **pad)
        self.cam_box.bind("<<ComboboxSelected>>", lambda e: self.update_link_row())
        self.btn_cam = ttk.Button(self, command=self.camera_settings_dialog, width=12)
        self.btn_cam.grid(row=0, column=2, sticky="w", padx=(0, 10), pady=5)

        self.link_row = ttk.Frame(self)
        self.link_row.grid(row=1, column=0, columnspan=3, sticky="w", padx=10)
        self.lbl_link = ttk.Label(self.link_row)
        self.lbl_link.grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.link_var = tk.StringVar(value=self.cfg.get("link", ""))
        self.link_entry = ttk.Entry(self.link_row, textvariable=self.link_var, width=52)
        self.link_entry.grid(row=0, column=1, sticky="w")
        self.lbl_link_hint = ttk.Label(self.link_row, foreground="gray", wraplength=470, justify="left")
        self.lbl_link_hint.grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 4))

        self.lbl_copies = ttk.Label(self)
        self.lbl_copies.grid(row=2, column=0, sticky="w", **pad)
        self.copies = tk.IntVar(value=self.cfg.get("copies", 2))
        self.spin = ttk.Spinbox(self, from_=1, to=1, textvariable=self.copies, width=5)
        self.spin.grid(row=2, column=1, sticky="w", **pad)

        # one row per copy: mirror, output size, settings
        self.rows_frame = ttk.Frame(self)
        self.rows_frame.grid(row=3, column=0, columnspan=3, sticky="w", padx=10, pady=2)
        self.copy_rows = []  # (frame, label, mirror_var, checkbutton, size_box, settings_button)
        for i in range(MAX_COPIES):
            fr = ttk.Frame(self.rows_frame)
            fr.grid(row=i, column=0, sticky="w", pady=1)
            lbl = ttk.Label(fr, width=9)
            lbl.grid(row=0, column=0, sticky="w")
            var = tk.BooleanVar(value=self.copy_cfg[i]["mirror"])
            chk = ttk.Checkbutton(fr, variable=var, command=lambda i=i: self.on_mirror(i))
            chk.grid(row=0, column=1, sticky="w", padx=(0, 12))
            box = ttk.Combobox(fr, state="readonly", width=16)
            box.grid(row=0, column=2, sticky="w", padx=(0, 12))
            box.bind("<<ComboboxSelected>>", lambda e, i=i: self.on_size(i))
            btn = ttk.Button(fr, command=lambda i=i: self.copy_settings_dialog(i), width=12)
            btn.grid(row=0, column=3, sticky="w")
            self.copy_rows.append((fr, lbl, var, chk, box, btn))

        row = ttk.Frame(self)
        row.grid(row=4, column=0, columnspan=3, **pad)
        self.btn = ttk.Button(row, command=self.toggle, width=12)
        self.btn.pack(side="left", padx=4)
        self.btn_setup = ttk.Button(row, command=self.setup_dialog)
        self.btn_setup.pack(side="left", padx=4)
        self.btn_plugins = ttk.Button(row, command=self.plugins_dialog)
        self.btn_plugins.pack(side="left", padx=4)
        self.lang_box = ttk.Combobox(row, values=list(LANG_NAMES.values()), state="readonly", width=9)
        self.lang_box.set(LANG_NAMES.get(_lang, "English"))
        self.lang_box.pack(side="left", padx=4)
        self.lang_box.bind("<<ComboboxSelected>>", self.change_language)

        self.blank = tk.PhotoImage(width=320, height=180)
        self.preview = tk.Label(self, image=self.blank, bg="black", borderwidth=0)
        self.preview.grid(row=5, column=0, columnspan=3, **pad)

        self.status = ttk.Label(self, wraplength=470, justify="left")
        self.status.grid(row=6, column=0, columnspan=3, sticky="w", **pad)

        self.protocol("WM_DELETE_WINDOW", self.close)
        self.apply_texts()
        self.refresh()
        self.copies.trace_add("write", lambda *_: self.update_copy_rows())
        self.update_copy_rows()
        self.tick()

    def report_callback_exception(self, exc, val, tb):
        logging.error("UI error", exc_info=(exc, val, tb))

    # ---- texts, source selection, per-copy rows
    def apply_texts(self):
        self.title(APP_NAME)
        self.lbl_cam.config(text=t("camera"))
        self.lbl_link.config(text=t("link"))
        self.lbl_link_hint.config(text=t("link_hint"))
        self.lbl_copies.config(text=t("copies"))
        self.btn_cam.config(text=t("settings"))
        self.btn.config(text=t("stop") if self.ui_running else t("start"))
        self.btn_setup.config(text=t("setup"))
        self.btn_plugins.config(text=t("plugins"))
        labels = size_labels()
        for i, (_fr, lbl, _var, chk, box, btn) in enumerate(self.copy_rows):
            lbl.config(text=t("copy_n", n=i + 1))
            chk.config(text=t("mirror"))
            btn.config(text=t("settings"))
            box.config(values=labels)
            box.current(SIZE_KEYS.index(self.copy_cfg[i]["size"]))
        self.update_source_values()

    def update_source_values(self):
        """Camera list + the 'Stream from link' entry at the end (keeps the current selection)."""
        names = [n for _, n in self.real]
        cur = self.cam_box.current()
        was_link = cur == len(names) and cur >= 0 and self.cam_box.get() != ""
        self.cam_box["values"] = names + [t("source_link")]
        if was_link:
            self.cam_box.current(len(names))

    def is_link_mode(self):
        return self.cam_box.current() == len(self.real)

    def update_link_row(self):
        if self.is_link_mode():
            self.link_row.grid()
        else:
            self.link_row.grid_remove()

    def n_copies(self):
        try:
            n = int(self.copies.get())
        except Exception:
            return 1
        return max(1, min(MAX_COPIES, n))

    def update_copy_rows(self):
        n = self.n_copies()
        for i, row in enumerate(self.copy_rows):
            if i < n:
                row[0].grid()
            else:
                row[0].grid_remove()

    def on_mirror(self, i):
        self.copy_cfg[i]["mirror"] = bool(self.copy_rows[i][2].get())  # live

    def on_size(self, i):
        self.copy_cfg[i]["size"] = SIZE_KEYS[self.copy_rows[i][4].current()]

    def change_language(self, _event=None):
        global _lang
        chosen = self.lang_box.get()
        for code, name in LANG_NAMES.items():
            if name == chosen:
                _lang = code
        self.cfg["lang"] = _lang
        save_settings(self.cfg)
        self.apply_texts()

    def refresh(self):
        devices = all_devices()
        self.real = [(i, n) for i, n in enumerate(devices) if not is_virtual(n, self.base)]
        if not self.real:
            self.real = [(i, f"Camera {i}") for i in range(3)]
        names = [n for _, n in self.real]
        self.cam_box["values"] = names + [t("source_link")]
        if self.cfg.get("source") == "link":
            self.cam_box.current(len(names))
        else:
            saved = self.cfg.get("camera")
            self.cam_box.current(names.index(saved) if saved in names else 0)
        self.update_link_row()
        self.vnames = sorted(n for n in devices if is_virtual(n, self.base))
        self.vnames.sort(key=capnum_from_name)
        vcount = len(self.vnames)
        self.spin.config(to=max(1, min(MAX_COPIES, vcount)))
        if vcount == 0:
            self.worker.status = ("status_no_vcams", {})
        elif self.n_copies() > vcount:
            self.copies.set(vcount)

    def set_running_ui(self, running):
        self.ui_running = running
        self.btn.config(text=t("stop") if running else t("start"))
        state = "disabled" if running else "readonly"
        self.cam_box.config(state=state)
        self.link_entry.config(state="disabled" if running else "normal")
        self.spin.config(state="disabled" if running else "normal")
        for b in (self.btn_cam, self.btn_setup, self.btn_plugins):
            b.config(state="disabled" if running else "normal")
        for row in self.copy_rows:
            row[4].config(state=state)  # output size needs a restart, the rest stays live
        if not running:
            self.preview.config(image=self.blank)

    def save_all(self, camera_name):
        self.cfg.update(
            camera=camera_name, source="link" if self.is_link_mode() else "camera",
            link=self.link_var.get().strip(), copies=self.n_copies(), res=self.capture_res,
            capture_fps=self.capture_fps, base=self.base,
            copy_opts=[dict(c) for c in self.copy_cfg])
        self.cfg.pop("mirror", None)
        save_settings(self.cfg)

    def toggle(self):
        if self.worker.running or self.ui_running:
            self.worker.stop()
            self.worker.status = ("status_stopped", {})
            self.set_running_ui(False)
            return
        if self.is_link_mode():
            source = normalize_stream_url(self.link_var.get())
            if not source:
                self.worker.status = ("status_need_link", {})
                return
            name = self.cfg.get("camera", "")
        else:
            source, name = self.real[self.cam_box.current()]
        vdevs = sorted(((capnum_from_name(n), n) for n in all_devices() if is_virtual(n, self.base)))
        n = self.n_copies()
        self.save_all(name)
        self.worker.start(source=source, copies=n, size=RESOLUTIONS[self.capture_res],
                          fps=self.capture_fps, copy_opts=self.copy_cfg[:n], vdevs=vdevs,
                          plugins=self.plugins)
        self.set_running_ui(True)

    # ---- dialogs
    def make_dialog(self, title):
        win = tk.Toplevel(self)
        win.title(title)
        win.resizable(False, False)
        win.transient(self)
        win.grab_set()
        return win

    def camera_settings_dialog(self):
        win = self.make_dialog(t("cam_settings_title"))
        pad = {"padx": 10, "pady": 6}
        ttk.Label(win, text=t("resolution")).grid(row=0, column=0, sticky="w", **pad)
        res = ttk.Combobox(win, values=list(RESOLUTIONS), state="readonly", width=14)
        res.set(self.capture_res)
        res.grid(row=0, column=1, sticky="w", **pad)
        ttk.Label(win, text=t("capture_fps")).grid(row=1, column=0, sticky="w", **pad)
        fps = ttk.Combobox(win, values=[str(v) for v in CAPTURE_FPS_CHOICES], state="readonly", width=14)
        fps.set(str(self.capture_fps) if self.capture_fps in CAPTURE_FPS_CHOICES else "30")
        fps.grid(row=1, column=1, sticky="w", **pad)

        def ok():
            self.capture_res = res.get()
            self.capture_fps = _num(fps.get(), 30, 5, 60)
            self.cfg.update(res=self.capture_res, capture_fps=self.capture_fps)
            save_settings(self.cfg)
            win.destroy()

        ttk.Button(win, text=t("ok"), command=ok).grid(row=2, column=0, columnspan=2, pady=10)

    def copy_settings_dialog(self, i):
        c = self.copy_cfg[i]
        win = self.make_dialog(t("copy_settings_title", n=i + 1))
        pad = {"padx": 10, "pady": 5}

        # name: planned feature, shown greyed out
        ttk.Label(win, text=t("name")).grid(row=0, column=0, sticky="w", **pad)
        shown = self.vnames[i] if i < len(self.vnames) else (self.base if i == 0 else f"{self.base} #{i + 1}")
        nf = ttk.Frame(win)
        nf.grid(row=0, column=1, sticky="w", **pad)
        name_var = tk.StringVar(value=shown)
        ttk.Entry(nf, textvariable=name_var, width=26, state="disabled").pack(side="left")
        ttk.Label(nf, text=t("soon"), foreground="gray").pack(side="left", padx=8)

        fps = ttk.Combobox(win, values=[t("size_same")] + [str(v) for v in OUT_FPS_CHOICES],
                           state="readonly", width=14)
        fps.current(OUT_FPS_CHOICES.index(c["fps"]) + 1 if c["fps"] in OUT_FPS_CHOICES else 0)
        zoom = tk.StringVar(value=str(c["zoom"]))
        rotate = ttk.Combobox(win, values=[f"{r}\u00b0" for r in ROTATIONS], state="readonly", width=14)
        rotate.current(ROTATIONS.index(c["rotate"]))
        brightness = tk.StringVar(value=str(c["brightness"]))
        contrast = tk.StringVar(value=str(c["contrast"]))
        rows = [("fps", fps),
                ("zoom", ttk.Spinbox(win, from_=100, to=400, increment=10, textvariable=zoom, width=8)),
                ("rotate", rotate),
                ("brightness", ttk.Spinbox(win, from_=-100, to=100, increment=5, textvariable=brightness, width=8)),
                ("contrast", ttk.Spinbox(win, from_=50, to=200, increment=5, textvariable=contrast, width=8))]
        for r, (key, widget) in enumerate(rows, start=1):
            ttk.Label(win, text=t(key)).grid(row=r, column=0, sticky="w", **pad)
            widget.grid(row=r, column=1, sticky="w", **pad)
        if self.ui_running:
            rotate.config(state="disabled")
            ttk.Label(win, text=t("restart_needed"), foreground="gray", wraplength=360, justify="left")\
                .grid(row=6, column=0, columnspan=2, sticky="w", **pad)

        def reset():
            fps.current(0)
            zoom.set("100")
            rotate.current(0)
            brightness.set("0")
            contrast.set("100")

        def ok():
            c["fps"] = OUT_FPS_CHOICES[fps.current() - 1] if fps.current() > 0 else 0
            c["zoom"] = _num(zoom.get(), c["zoom"], 100, 400)
            c["brightness"] = _num(brightness.get(), c["brightness"], -100, 100)
            c["contrast"] = _num(contrast.get(), c["contrast"], 50, 200)
            if not self.ui_running:
                c["rotate"] = ROTATIONS[rotate.current()]
            self.cfg["copy_opts"] = [dict(x) for x in self.copy_cfg]
            save_settings(self.cfg)
            win.destroy()

        bf = ttk.Frame(win)
        bf.grid(row=7, column=0, columnspan=2, pady=(8, 4))
        ttk.Button(bf, text=t("reset"), command=reset).pack(side="left", padx=6)
        ttk.Button(bf, text=t("ok"), command=ok).pack(side="left", padx=6)
        ttk.Label(win, text=t("dev_note"), foreground="gray").grid(row=8, column=0, columnspan=2, pady=(2, 10))

    def setup_dialog(self):
        if self.worker.running:
            self.toggle()
        win = self.make_dialog(t("setup_title"))
        pad = {"padx": 10, "pady": 6}
        ttk.Label(win, text=t("setup_name")).grid(row=0, column=0, sticky="w", **pad)
        name = tk.StringVar(value=self.base)
        ttk.Entry(win, textvariable=name, width=30).grid(row=1, column=0, sticky="w", **pad)
        ttk.Label(win, text=t("setup_count")).grid(row=2, column=0, sticky="w", **pad)
        count = tk.IntVar(value=max(self.n_copies(), 2))
        ttk.Spinbox(win, from_=1, to=10, textvariable=count, width=5)\
            .grid(row=3, column=0, sticky="w", **pad)
        ttk.Label(win, text=t("setup_note"), justify="left").grid(row=4, column=0, sticky="w", **pad)
        apply_btn = ttk.Button(win, text=t("setup_apply"))
        apply_btn.grid(row=5, column=0, **pad)

        def finished(err, base):
            if err:
                key, kw = err
                apply_btn.config(state="normal")
                self.worker.status = ("status_ready", {})
                messagebox.showerror(t("err_title"), t(key, **kw), parent=win)
                return
            self.cfg["base"] = base
            save_settings(self.cfg)
            messagebox.showinfo(t("restart_title"), t("restart_msg"), parent=win)
            self.restart()

        def apply():
            try:
                base = re.sub(r"[^A-Za-z0-9 _-]", "", name.get()).strip() or DEFAULT_BASE
                n = max(1, min(10, count.get()))
            except Exception:
                return
            apply_btn.config(state="disabled")
            self.worker.status = ("status_waiting_admin", {})

            def job():
                err = install_driver(base, n)
                self.events.put(lambda: finished(err, base))

            threading.Thread(target=job, daemon=True).start()

        apply_btn.config(command=apply)

    def plugins_dialog(self):
        self.plugins.discover()
        win = self.make_dialog(t("plugins_title"))
        pad = {"padx": 10, "pady": 6}
        ttk.Label(win, text=t("plugins_note"), wraplength=470, justify="left")\
            .grid(row=0, column=0, sticky="w", **pad)
        box = ttk.Frame(win)
        box.grid(row=1, column=0, sticky="w", padx=10)
        buttons = {}

        def open_settings(info):
            inst = self.plugins.get_instance(info.pid)
            if inst is None:
                messagebox.showerror(t("err_title"), t("plugin_load_failed", name=localized(info.name, _lang)),
                                     parent=win)
                return
            fn = getattr(inst, "settings_ui", None)
            if fn is None:
                messagebox.showinfo(t("plugins_title"), t("plugin_no_settings"), parent=win)
                return
            sw = tk.Toplevel(win)
            sw.transient(win)
            sw.grab_set()
            try:
                fn(sw)
            except Exception:
                logging.exception("Plugin settings failed")
                sw.destroy()
                messagebox.showerror(t("err_title"), t("plugin_load_failed", name=localized(info.name, _lang)),
                                     parent=win)

        def toggle(info, var):
            if var.get():
                if not info.builtin and not self.plugins.is_trusted(info.pid):
                    if not messagebox.askyesno(t("plugins_warn_title"),
                                               t("plugins_warn_msg", name=localized(info.name, _lang)),
                                               icon="warning", parent=win):
                        var.set(False)
                        return
                    self.plugins.trust(info.pid)
                self.plugins.failed.pop(info.pid, None)
            self.plugins.set_enabled(info.pid, bool(var.get()))
            buttons[info.pid].config(state="normal" if var.get() else "disabled")

        for r, info in enumerate(self.plugins.infos):
            var = tk.BooleanVar(value=self.plugins.is_enabled(info.pid))
            title = localized(info.name, _lang) + (f"  v{info.version}" if info.version else "")
            if not info.builtin:
                title += f"  ({t('plugin_external')})"
            ttk.Checkbutton(box, text=title, variable=var,
                            command=lambda i=info, v=var: toggle(i, v))\
                .grid(row=2 * r, column=0, sticky="w", pady=(8, 0))
            btn = ttk.Button(box, text=t("plugin_settings"), command=lambda i=info: open_settings(i),
                             state="normal" if var.get() else "disabled")
            btn.grid(row=2 * r, column=1, rowspan=2, padx=12)
            buttons[info.pid] = btn
            ttk.Label(box, text=localized(info.description, _lang), wraplength=360, justify="left")\
                .grid(row=2 * r + 1, column=0, sticky="w", padx=(24, 0))

        bottom = ttk.Frame(win)
        bottom.grid(row=2, column=0, **pad)

        def open_folder():
            try:
                os.makedirs(PLUGIN_DIR, exist_ok=True)
                os.startfile(PLUGIN_DIR)
            except Exception:
                logging.exception("Could not open the plugin folder")

        ttk.Button(bottom, text=t("plugins_folder"), command=open_folder).pack(side="left", padx=6)
        ttk.Button(bottom, text=t("plugins_close"), command=win.destroy).pack(side="left", padx=6)

    def restart(self):
        """Restarts the program so it sees the new cameras with a clean state."""
        self.worker.stop()
        cmd = [sys.executable] if getattr(sys, "frozen", False) \
            else [sys.executable, os.path.abspath(__file__)]
        env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")
        try:
            subprocess.Popen(cmd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, creationflags=0x00000008 | 0x00000200)
        except Exception:
            logging.exception("Restart failed")
        self.destroy()

    def tick(self):
        while True:
            try:
                self.events.get_nowait()()
            except queue.Empty:
                break
        frame = self.worker.latest
        if frame is not None:
            small = cv2.resize(frame, (320, 180))
            img = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(small, cv2.COLOR_BGR2RGB)))
            self.preview.config(image=img)
            self.preview.image = img
        key, kw = self.worker.status
        lines = [t(key, **kw)] + [v for v in list(self.plugins.info.values()) if v]
        for pid, kind in list(self.plugins.failed.items()):
            if self.plugins.is_enabled(pid):
                lines.append(t("plugin_load_failed" if kind == "load" else "plugin_failed",
                               name=self.plugins.display_name(pid)))
        self.status.config(text="\n".join(lines))
        if self.ui_running and not self.worker.running:
            self.set_running_ui(False)  # the worker stopped by itself (error)
        self.after(40, self.tick)

    def close(self):
        self.worker.stop()
        self.destroy()


if __name__ == "__main__":
    setup_logging()
    App().mainloop()
