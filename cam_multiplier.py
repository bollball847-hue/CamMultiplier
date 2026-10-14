"""
Cam Multiplier
One webcam, several virtual cameras. For OBS, Discord, Teams and more.
Requires the Unity Capture driver (bundled with the installer).

License: GPL-2.0 (because of the pyvirtualcam dependency), see THIRD_PARTY_LICENSES.txt
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

import cv2
import pyvirtualcam
from PIL import Image, ImageTk

try:
    from pygrabber.dshow_graph import FilterGraph
except Exception:
    FilterGraph = None

APP_NAME = "Cam Multiplier"
DEFAULT_BASE = "Cam Multiplier"
FPS = 30
RESOLUTIONS = {"1280 x 720": (1280, 720), "1920 x 1080": (1920, 1080)}


# ----------------------------------------------------------------- languages
# To add a language: copy the "en" block, translate the values, and add the
# language to LANG_NAMES. Missing keys fall back to English.
LANG_NAMES = {"en": "English", "de": "Deutsch"}

STRINGS = {
    "en": {
        "camera": "Camera",
        "copies": "Number of copies",
        "resolution": "Resolution",
        "mirror": "Mirror image",
        "start": "Start",
        "stop": "Stop",
        "setup": "Set up cameras",
        "language": "Language",
        "status_ready": "Ready.",
        "status_opening": "Opening camera ...",
        "status_no_frame": "No image from the camera. Close OBS and other camera apps, then try again.",
        "status_not_enough": "Only {found} virtual camera(s) installed, {wanted} requested. Use 'Set up cameras' to change this.",
        "status_vcam_error": "Could not open virtual camera: {err}",
        "status_running": "Running: {names}",
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
        "copies": "Anzahl Kopien",
        "resolution": "Auflösung",
        "mirror": "Bild spiegeln",
        "start": "Start",
        "stop": "Stopp",
        "setup": "Kameras einrichten",
        "language": "Sprache",
        "status_ready": "Bereit.",
        "status_opening": "Kamera wird geöffnet ...",
        "status_no_frame": "Kein Bild von der Kamera. OBS und andere Kamera-Programme schließen und erneut versuchen.",
        "status_not_enough": "Nur {found} virtuelle Kamera(s) installiert, {wanted} gewünscht. Über 'Kameras einrichten' ändern.",
        "status_vcam_error": "Virtuelle Kamera konnte nicht geöffnet werden: {err}",
        "status_running": "Läuft: {names}",
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


# ------------------------------------------------------------------ settings
def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


DATA_DIR = os.path.join(os.environ.get("APPDATA", app_dir()), "CamMultiplier")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
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


def open_camera(index, width, height):
    """Tries backends and modes until a real image arrives."""
    for be in (cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY):
        for mjpg in (False, True):
            for size in (True, False):
                cap = cv2.VideoCapture(index, be)
                if not cap.isOpened():
                    cap.release()
                    continue
                if mjpg:
                    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
                if size:
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                    cap.set(cv2.CAP_PROP_FPS, FPS)
                for _ in range(20):
                    ok, frame = cap.read()
                    if ok and frame is not None and frame.mean() > 1:
                        return cap
                    time.sleep(0.1)
                cap.release()
    return None


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
        self.latest = None
        self.status = ("status_ready", {})

    def start(self, **opts):
        self.stop()
        self.running = True
        self.thread = threading.Thread(target=self._run, kwargs=opts, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=3)
        self.thread = None
        self.latest = None

    def _run(self, index, copies, size, mirror, vnames):
        self.status = ("status_opening", {})
        cap = open_camera(index, *size)
        if cap is None:
            self.status = ("status_no_frame", {})
            self.running = False
            return
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or size[0]
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or size[1]
        if len(vnames) < copies:
            cap.release()
            self.status = ("status_not_enough", {"found": len(vnames), "wanted": copies})
            self.running = False
            return
        cams = []
        try:
            for name in vnames[:copies]:
                cams.append(pyvirtualcam.Camera(width=w, height=h, fps=FPS,
                                                device=name, backend="unitycapture"))
        except Exception as e:
            logging.exception("Virtual camera open failed")
            for c in cams:
                c.close()
            cap.release()
            self.status = ("status_vcam_error", {"err": str(e)})
            self.running = False
            return
        self.status = ("status_running", {"names": ", ".join(vnames[:copies])})
        try:
            while self.running:
                ok, frame = cap.read()
                if not ok:
                    time.sleep(0.02)
                    continue
                if mirror:
                    frame = cv2.flip(frame, 1)
                self.latest = frame
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                for c in cams:
                    c.send(rgb)
                cams[0].sleep_until_next_frame()
        finally:
            for c in cams:
                c.close()
            cap.release()


# ------------------------------------------------------------------------ UI
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        global _lang
        self.resizable(False, False)
        self.worker = Worker()
        self.cfg = load_settings()
        _lang = self.cfg.get("lang") or detect_language()
        self.base = self.cfg.get("base", DEFAULT_BASE)
        self.real = []
        self.events = queue.Queue()  # lets background threads talk to the UI safely

        pad = {"padx": 10, "pady": 5}
        self.lbl_cam = ttk.Label(self)
        self.lbl_cam.grid(row=0, column=0, sticky="w", **pad)
        self.cam_box = ttk.Combobox(self, state="readonly", width=38)
        self.cam_box.grid(row=0, column=1, sticky="w", **pad)

        self.lbl_copies = ttk.Label(self)
        self.lbl_copies.grid(row=1, column=0, sticky="w", **pad)
        self.copies = tk.IntVar(value=self.cfg.get("copies", 2))
        self.spin = ttk.Spinbox(self, from_=1, to=1, textvariable=self.copies, width=5)
        self.spin.grid(row=1, column=1, sticky="w", **pad)

        self.lbl_res = ttk.Label(self)
        self.lbl_res.grid(row=2, column=0, sticky="w", **pad)
        self.res = ttk.Combobox(self, values=list(RESOLUTIONS), state="readonly", width=14)
        self.res.set(self.cfg.get("res", "1280 x 720"))
        self.res.grid(row=2, column=1, sticky="w", **pad)

        self.mirror = tk.BooleanVar(value=self.cfg.get("mirror", False))
        self.chk_mirror = ttk.Checkbutton(self, variable=self.mirror)
        self.chk_mirror.grid(row=3, column=1, sticky="w", **pad)

        row = ttk.Frame(self)
        row.grid(row=4, column=0, columnspan=2, **pad)
        self.btn = ttk.Button(row, command=self.toggle, width=12)
        self.btn.pack(side="left", padx=4)
        self.btn_setup = ttk.Button(row, command=self.setup_dialog)
        self.btn_setup.pack(side="left", padx=4)
        self.lang_box = ttk.Combobox(row, values=list(LANG_NAMES.values()), state="readonly", width=9)
        self.lang_box.set(LANG_NAMES.get(_lang, "English"))
        self.lang_box.pack(side="left", padx=4)
        self.lang_box.bind("<<ComboboxSelected>>", self.change_language)

        self.blank = tk.PhotoImage(width=320, height=180)
        self.preview = tk.Label(self, image=self.blank, bg="black", borderwidth=0)
        self.preview.grid(row=5, column=0, columnspan=2, **pad)

        self.status = ttk.Label(self, wraplength=420, justify="left")
        self.status.grid(row=6, column=0, columnspan=2, sticky="w", **pad)

        self.protocol("WM_DELETE_WINDOW", self.close)
        self.apply_texts()
        self.refresh()
        self.tick()

    def report_callback_exception(self, exc, val, tb):
        logging.error("UI error", exc_info=(exc, val, tb))

    def apply_texts(self):
        self.title(APP_NAME)
        self.lbl_cam.config(text=t("camera"))
        self.lbl_copies.config(text=t("copies"))
        self.lbl_res.config(text=t("resolution"))
        self.chk_mirror.config(text=t("mirror"))
        self.btn.config(text=t("stop") if self.worker.running else t("start"))
        self.btn_setup.config(text=t("setup"))

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
        self.cam_box["values"] = names
        saved = self.cfg.get("camera")
        self.cam_box.current(names.index(saved) if saved in names else 0)
        vcount = len([n for n in devices if is_virtual(n, self.base)])
        self.spin.config(to=max(1, vcount))
        if vcount == 0:
            self.worker.status = ("status_no_vcams", {})
        elif self.copies.get() > vcount:
            self.copies.set(vcount)

    def toggle(self):
        if self.worker.running:
            self.worker.stop()
            self.btn.config(text=t("start"))
            self.worker.status = ("status_stopped", {})
            self.preview.config(image=self.blank)
            return
        idx, name = self.real[self.cam_box.current()]
        vnames = [n for n in all_devices() if is_virtual(n, self.base)]
        self.cfg.update(camera=name, copies=self.copies.get(), res=self.res.get(),
                        mirror=self.mirror.get(), base=self.base)
        save_settings(self.cfg)
        self.worker.start(index=idx, copies=self.copies.get(), size=RESOLUTIONS[self.res.get()],
                          mirror=self.mirror.get(), vnames=vnames)
        self.btn.config(text=t("stop"))

    def setup_dialog(self):
        if self.worker.running:
            self.toggle()
        win = tk.Toplevel(self)
        win.title(t("setup_title"))
        win.resizable(False, False)
        win.transient(self)
        win.grab_set()
        pad = {"padx": 10, "pady": 6}
        ttk.Label(win, text=t("setup_name")).grid(row=0, column=0, sticky="w", **pad)
        name = tk.StringVar(value=self.base)
        ttk.Entry(win, textvariable=name, width=30).grid(row=1, column=0, sticky="w", **pad)
        ttk.Label(win, text=t("setup_count")).grid(row=2, column=0, sticky="w", **pad)
        count = tk.IntVar(value=max(self.copies.get(), 2))
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
        self.status.config(text=t(key, **kw))
        if not self.worker.running and self.btn.cget("text") == t("stop"):
            self.btn.config(text=t("start"))
        self.after(40, self.tick)

    def close(self):
        self.worker.stop()
        self.destroy()


if __name__ == "__main__":
    setup_logging()
    App().mainloop()
