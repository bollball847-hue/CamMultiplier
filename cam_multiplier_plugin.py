"""
Plugin system for Cam Multiplier (API version 1).

A plugin is a Python class. It only needs the methods it actually uses:

    on_start(info)              called when streaming starts
                                info = {"copies": 2, "names": [...], "sizes": [[w, h], ...], "fps": 30}
    on_frame(copy_index, frame) called for every frame of every copy (copy_index starts at 0).
                                frame is a read-only BGR image (numpy array).
                                Return a NEW frame of the same shape to change the picture,
                                or None to leave it unchanged.
    on_stop()                   called when streaming stops
    settings_ui(parent)         optional: fill the given tkinter Toplevel with settings widgets

See PLUGINS.md for details and an example.
"""
import importlib.util
import json
import logging
import os
import re
import sys

API_VERSION = 1
MAX_ERRORS = 5  # a plugin is switched off for the session after this many errors


def localized(value, lang):
    """Plugin names/descriptions may be a plain string or a dict like {"en": "...", "de": "..."}."""
    if isinstance(value, dict):
        return value.get(lang) or value.get("en") or next(iter(value.values()), "")
    return value or ""


class Plugin:
    """Optional base class for plugins (duck typing works too)."""
    id = ""
    name = "Plugin"
    description = ""
    version = "1.0"
    priority = 0  # order of on_frame: effects 0, plugins that only forward the picture 100

    def __init__(self, api):
        self.api = api

    def on_start(self, info):
        pass

    def on_frame(self, copy_index, frame):
        return None

    def on_stop(self):
        pass


class PluginApi:
    """What a plugin gets in its constructor."""
    api_version = API_VERSION

    def __init__(self, manager, plugin_id):
        self._m = manager
        self.plugin_id = plugin_id

    @property
    def lang(self):
        return self._m.lang()

    @property
    def data_dir(self):
        d = os.path.join(self._m.data_dir, self.plugin_id)
        os.makedirs(d, exist_ok=True)
        return d

    def get_setting(self, key, default=None):
        return self._m.cfg.get("plugin_settings", {}).get(self.plugin_id, {}).get(key, default)

    def set_setting(self, key, value):
        self._m.cfg.setdefault("plugin_settings", {}).setdefault(self.plugin_id, {})[key] = value
        self._m.save()

    def set_info(self, text):
        """Shows a line of text under the status in the main window (None removes it)."""
        if text:
            self._m.info[self.plugin_id] = text
        else:
            self._m.info.pop(self.plugin_id, None)

    def log(self, message):
        logging.info("[plugin %s] %s", self.plugin_id, message)


class PluginInfo:
    def __init__(self, pid, name, description, version, builtin, cls=None,
                 folder=None, entry=None, class_name=None):
        self.pid = pid
        self.name = name
        self.description = description
        self.version = version
        self.builtin = builtin
        self.cls = cls
        self.folder = folder
        self.entry = entry
        self.class_name = class_name


class PluginManager:
    def __init__(self, cfg, save, lang, plugin_dir, data_dir, builtin=()):
        self.cfg = cfg            # the app's settings dict (shared, never replaced)
        self.save = save          # callable that writes the settings
        self.lang = lang          # callable returning the current language code
        self.plugin_dir = plugin_dir
        self.data_dir = data_dir
        self.builtin = list(builtin)
        self.infos = []
        self.instances = {}
        self.active = []          # ids of plugins started for the current run
        self.frame_plugins = []
        self.errors = {}          # error counter per plugin
        self.failed = {}          # pid -> "load" | "runtime"
        self.info = {}            # pid -> status line (set by plugins)
        self.discover()

    # ---- discovery (reads manifests only, never runs external plugin code)
    def discover(self):
        self.infos = []
        seen = set()
        for cls in self.builtin:
            self.infos.append(PluginInfo(cls.id, cls.name, cls.description, cls.version, True, cls=cls))
            seen.add(cls.id)
        if not os.path.isdir(self.plugin_dir):
            return
        for entry in sorted(os.listdir(self.plugin_dir)):
            folder = os.path.join(self.plugin_dir, entry)
            manifest = os.path.join(folder, "plugin.json")
            if not (os.path.isdir(folder) and os.path.isfile(manifest)):
                continue
            try:
                with open(manifest, encoding="utf-8") as f:
                    m = json.load(f)
                pid = str(m["id"])
                if not re.fullmatch(r"[a-z0-9_-]{1,40}", pid) or pid in seen:
                    raise ValueError("invalid or duplicate id")
                if int(m.get("api", 1)) > API_VERSION:
                    raise ValueError("plugin needs a newer Cam Multiplier")
                entry_file = os.path.normpath(os.path.join(folder, m.get("entry", "plugin.py")))
                if not entry_file.startswith(os.path.normpath(folder) + os.sep) or not os.path.isfile(entry_file):
                    raise ValueError("entry file missing or outside the plugin folder")
                self.infos.append(PluginInfo(
                    pid, m.get("name", pid), m.get("description", ""), str(m.get("version", "")),
                    False, folder=folder, entry=entry_file, class_name=m.get("class", "PluginClass")))
                seen.add(pid)
            except Exception:
                logging.exception("Ignoring plugin manifest %s", manifest)

    def find(self, pid):
        return next((i for i in self.infos if i.pid == pid), None)

    def display_name(self, pid):
        info = self.find(pid)
        return localized(info.name, self.lang()) if info else pid

    # ---- enabling and trust
    def is_enabled(self, pid):
        return pid in self.cfg.get("plugins_enabled", [])

    def set_enabled(self, pid, on):
        lst = [p for p in self.cfg.get("plugins_enabled", []) if p != pid]
        if on:
            lst.append(pid)
        self.cfg["plugins_enabled"] = lst
        self.save()

    def is_trusted(self, pid):
        info = self.find(pid)
        return bool(info and (info.builtin or pid in self.cfg.get("plugins_trusted", [])))

    def trust(self, pid):
        lst = [p for p in self.cfg.get("plugins_trusted", []) if p != pid]
        lst.append(pid)
        self.cfg["plugins_trusted"] = lst
        self.save()

    # ---- loading
    def get_instance(self, pid):
        if pid in self.instances:
            return self.instances[pid]
        info = self.find(pid)
        if info is None or not self.is_trusted(pid):
            return None
        try:
            cls = info.cls or self._load_external(info)
            self.instances[pid] = cls(PluginApi(self, pid))
            self.failed.pop(pid, None)
        except Exception:
            logging.exception("Plugin %s could not be loaded", pid)
            self.failed[pid] = "load"
            return None
        return self.instances[pid]

    def _load_external(self, info):
        name = "cm_plugin_" + info.pid.replace("-", "_")
        if info.folder not in sys.path:
            sys.path.insert(0, info.folder)
        spec = importlib.util.spec_from_file_location(name, info.entry)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return getattr(module, info.class_name)

    # ---- running
    def start_all(self, run_info):
        self.active = []
        self.frame_plugins = []
        self.errors = {}
        for pid in list(self.cfg.get("plugins_enabled", [])):
            inst = self.get_instance(pid)
            if inst is None:
                continue
            try:
                fn = getattr(inst, "on_start", None)
                if fn:
                    fn(dict(run_info))
            except Exception:
                self._fail(pid, "on_start", immediate=True)
                continue
            self.active.append(pid)
            if getattr(inst, "on_frame", None):
                self.frame_plugins.append(pid)
        # effects (priority 0) run before plugins that only send the picture elsewhere (priority 100)
        self.frame_plugins.sort(key=lambda p: getattr(self.instances[p], "priority", 0))

    def has_frame_hooks(self):
        return bool(self.frame_plugins)

    def on_frame(self, copy_index, frame):
        for pid in list(self.frame_plugins):
            try:
                out = self.instances[pid].on_frame(copy_index, frame)
            except Exception:
                self._fail(pid, "on_frame")
                continue
            if out is None or out is frame:
                continue
            if getattr(out, "shape", None) == frame.shape and getattr(out, "dtype", None) == frame.dtype:
                frame = out
            else:
                self._fail(pid, "on_frame returned a frame with the wrong shape or type")
        return frame

    def stop_all(self):
        for pid in reversed(self.active):
            fn = getattr(self.instances.get(pid), "on_stop", None)
            try:
                if fn:
                    fn()
            except Exception:
                logging.exception("Plugin %s: on_stop failed", pid)
        self.active = []
        self.frame_plugins = []
        self.info.clear()

    def _fail(self, pid, where, immediate=False):
        logging.exception("Plugin %s: error in %s", pid, where)
        self.errors[pid] = self.errors.get(pid, 0) + 1
        if immediate or self.errors[pid] >= MAX_ERRORS:
            self.failed[pid] = "runtime"
            if pid in self.frame_plugins:
                self.frame_plugins.remove(pid)
            self.info.pop(pid, None)
