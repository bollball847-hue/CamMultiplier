# Cam Multiplier plugins

Plugins add features to Cam Multiplier without changing the program. A plugin can **change the picture**
of a virtual camera (effects) or **forward the picture somewhere else** (streaming, recording, ...).

Open **Plugins** in the program to switch plugins on or off and to open their settings.
Changes apply the next time you press **Start**.

## Built-in plugins

| Plugin | What it does |
|---|---|
| **LAN Stream** | Shows the copies in a browser on another device in the same network. While running, the link is shown in the main window, e.g. `http://192.168.1.23:8090/?key=ab12cd34`. Open it on a phone or tablet, or use it as a *Browser source* in OBS on another PC. |

Notes for LAN Stream: the link contains a random access key, but the stream is **not encrypted**. Only use it in
networks you trust. On first start Windows may ask to allow network access: allow **private networks**.
Settings: port, JPEG quality, max. frames per second, max. width.

## Installing an external plugin

1. In the program: **Plugins -> Open plugin folder** (it is `%APPDATA%\CamMultiplier\plugins`).
2. Copy the plugin folder into it. Every plugin folder contains a `plugin.json` and the plugin code.
3. Reopen **Plugins**, tick the plugin and confirm the warning.

> **Security:** a plugin is Python code that runs with the same rights as Cam Multiplier. Only install
> plugins whose source you trust. Cam Multiplier never loads external code before you tick the plugin.

## Writing a plugin

A plugin folder looks like this (a full example is in `examples/plugin_grayscale`):

```
my_plugin/
    plugin.json
    plugin.py
```

**plugin.json**

```json
{
  "id": "my-plugin",
  "name": {"en": "My plugin", "de": "Mein Plugin"},
  "description": {"en": "What it does.", "de": "Was es macht."},
  "version": "1.0",
  "api": 1,
  "entry": "plugin.py",
  "class": "MyPlugin"
}
```

`id` must be unique (lowercase letters, digits, `-`, `_`). `name` and `description` can be plain strings or
dictionaries with one text per language.

**plugin.py**

```python
class MyPlugin:
    priority = 0   # optional: effects 0 (default), plugins that only forward the picture 100

    def __init__(self, api):
        self.api = api

    def on_start(self, info):
        # info = {"copies": 2, "names": ["Cam Multiplier", ...], "sizes": [[1280, 720], ...], "fps": 30}
        pass

    def on_frame(self, copy_index, frame):
        # copy_index starts at 0. 'frame' is a read-only BGR image (numpy array).
        # Return a NEW image with the same shape and dtype to change the picture, or None for no change.
        return None

    def on_stop(self):
        pass

    def settings_ui(self, parent):
        # optional: 'parent' is a tkinter Toplevel, add your widgets to it
        pass
```

You only need the methods you use. `on_frame` runs for every frame of every copy, so keep it fast and never
block in it (do slow work in your own thread). If a plugin raises errors repeatedly it is switched off for the
session and the error is written to `%APPDATA%\CamMultiplier\app.log`.

**The `api` object**

| | |
|---|---|
| `api.lang` | current interface language, `"en"` or `"de"` |
| `api.get_setting(key, default)` / `api.set_setting(key, value)` | settings stored for your plugin |
| `api.data_dir` | a folder where your plugin may store files |
| `api.set_info(text)` | shows a line under the status in the main window (`None` removes it) |
| `api.log(text)` | writes to `app.log` |

**Available libraries:** the installed program contains Python, `cv2` (OpenCV), `numpy`, `PIL` (Pillow),
`tkinter` and the standard library modules that Cam Multiplier itself uses (e.g. `json`, `threading`, `socket`,
`http.server`). Other third-party libraries are not available in the installed version.

**Order:** plugins with a lower `priority` run first. Effects change the picture; sinks such as LAN Stream
(priority 100) run last and therefore see the final picture.

## Sharing a plugin

Zip the plugin folder and share it, for example as a GitHub repository or release. Please state clearly what the
plugin does and that it runs code on the user's PC.
