<p align="center"><img src="assets/logo.png" alt="Cam Multiplier" width="160"></p>

# Cam Multiplier

Duplicate **one** webcam into **several virtual cameras** on Windows.

Many apps (and OBS Studio in particular) cannot open the same webcam twice. Cam Multiplier opens your
webcam once and publishes the picture on as many virtual cameras as you need. Each app (or each source
in OBS) can then use its own virtual camera at the same time.

Typical use: one camera source in OBS stays untouched while a second copy gets a background-removal
filter, so you can place effects behind and in front of yourself.

## Features

- Pick your webcam and see a live preview, or use a network stream (link) as the source
- 1 to 10 virtual cameras from a single source
- Settings per copy: mirroring, output size, frame rate, zoom, rotation, brightness and contrast
- Automatic reconnect when the webcam is unplugged or the stream stops
- Plugins, including a built-in LAN stream to watch the copies on a phone or another PC
- Choose the name of the virtual cameras (a number is added automatically)
- 720p or 1080p camera resolution
- English and German interface (switchable in the program)
- Remembers your settings

<img width="597" height="562" alt="grafik" src="https://github.com/user-attachments/assets/723a98bc-c389-4635-9c1c-1103d32d7524" />

## Requirements

- Windows 10 or 11, 64-bit
- A webcam that works in other Windows apps
- Administrator permission once, to register the virtual cameras

## Installation (recommended)

1. Download `CamMultiplier-Setup.exe` from the [Releases](https://github.com/bollball847-hue/CamMultiplier/releases) page.
2. Run it. If Windows SmartScreen shows a warning, click **More info** and then **Run anyway**
   (the installer is not code-signed).
3. Start **Cam Multiplier**.

The installer also sets up 3 virtual cameras named "Cam Multiplier", "Cam Multiplier #2" and
"Cam Multiplier #3". You can change the name and the number any time with **Set up cameras**.

## Usage

1. Close every app that is currently using your webcam (including OBS sources that use it directly).
2. Start Cam Multiplier, choose your webcam, set the number of copies and press **Start**.
3. In OBS Studio add a **Video Capture Device** source for each copy and select one of the
   "Cam Multiplier" devices per source.
4. Keep Cam Multiplier running while you use the virtual cameras.

### Using a network stream as the source

Choose **Stream from link ...** in the camera list and paste a link. This can be the link that the
**LAN Stream** plugin of another Cam Multiplier shows (for example from a second PC), or any other
http/rtsp video stream. The copies work exactly as with a webcam.

## Plugins

Open **Plugins** in the program to switch plugins on or off. Changes apply the next time you press **Start**.

- **LAN Stream** (built in): watch the copies in a browser on another device in the same network. While it is
  running, the link is shown in the main window. The link contains a random access key, but the stream is not
  encrypted, so only use it in networks you trust. On first start Windows may ask to allow network access:
  allow private networks.
- **External plugins:** copy a plugin folder into `%APPDATA%\CamMultiplier\plugins` (button **Open plugin folder**).
  Plugins are Python code and run with the same rights as the program, so only install plugins you trust.
  How to write one: see [PLUGINS.md](PLUGINS.md).

## Run from source (Python)

Needs Python 3.10 or newer on Windows.

```
git clone https://github.com/bollball847-hue/CamMultiplier.git
cd CamMultiplier
pip install -r requirements.txt
python cam_multiplier.py
```

The virtual cameras need the Unity Capture driver. Download `UnityCaptureFilter32.dll` and
`UnityCaptureFilter64.dll` from the [Unity Capture repository](https://github.com/schellingb/UnityCapture)
(folder `Install`), put them in a folder called `driver` next to `cam_multiplier.py`, and click
**Set up cameras** in the program.

## Build the installer yourself

1. Install Python and [Inno Setup 6](https://jrsoftware.org/isinfo.php).
2. Run `build.bat`. It downloads the driver files, builds the program with PyInstaller and creates
   `installer_output\CamMultiplier-Setup.exe`.

## Troubleshooting

| Problem | What to do |
|---|---|
| "No image from the camera" | Close OBS, browsers, Teams, Zoom and the Windows Camera app. Only one program can use the physical webcam. Remove webcam sources in OBS and use the virtual cameras instead. |
| Laptop shows several cameras | Choose the one that shows a normal picture. Infrared (Windows Hello) cameras only show black or grey. |
| Virtual cameras missing in OBS | Click **Set up cameras**, then restart OBS. |
| Program closes unexpectedly | Send the files in `%APPDATA%\CamMultiplier\` (`app.log`, `crash.log`) with a new issue. |
## Credits and license

Cam Multiplier is licensed under the **[MIT / GPL-2.0]** license (see `LICENSE`).

It uses [Unity Capture](https://github.com/schellingb/UnityCapture) by Bernhard Schelling (MIT license)
for the virtual camera devices, [OpenCV](https://opencv.org/), [Pillow](https://python-pillow.org/) and
[pygrabber](https://github.com/andreaschiavinato/python_grabber). See `THIRD_PARTY_LICENSES.txt`.

Not affiliated with OBS Studio, Microsoft or any other mentioned product.
