# Cam Multiplier

Duplicate **one** webcam into **several virtual cameras** on Windows.

Many apps (and OBS Studio in particular) cannot open the same webcam twice. Cam Multiplier opens your
webcam once and publishes the picture on as many virtual cameras as you need. Each app (or each source
in OBS) can then use its own virtual camera at the same time.

Typical use: one camera source in OBS stays untouched while a second copy gets a background-removal
filter, so you can place effects behind and in front of yourself.

## Features

- Pick your webcam and see a live preview
- 1 to 10 virtual cameras from a single webcam
- Choose the name of the virtual cameras (a number is added automatically)
- 720p or 1080p, optional mirroring
- English and German interface (switchable in the program)
- Remembers your settings
  
 <img width="481" height="505" alt="programm-preview" src="https://github.com/user-attachments/assets/b18774dd-4a1a-418b-821e-d9588187967e" />

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

**Verify the download:**
SHA256 of `CamMultiplier-Setup.exe`: `2d73f3ced199a290f4c5dfc616048b1b74dc6250ace32ff46090321bd2a9828a`
 ([VirusTotal scan](https://www.virustotal.com/gui/file/2d73f3ced199a290f4c5dfc616048b1b74dc6250ace32ff46090321bd2a9828a))

## Usage

1. Close every app that is currently using your webcam (including OBS sources that use it directly).
2. Start Cam Multiplier, choose your webcam, set the number of copies and press **Start**.
3. In OBS Studio add a **Video Capture Device** source for each copy and select one of the
   "Cam Multiplier" devices per source.
4. Keep Cam Multiplier running while you use the virtual cameras.

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

Cam Multiplier is licensed under the **GPL-2.0** (see `LICENSE`).

It uses [Unity Capture](https://github.com/schellingb/UnityCapture) by Bernhard Schelling (MIT license)
for the virtual camera devices, [pyvirtualcam](https://github.com/letmaik/pyvirtualcam) (GPL-2.0),
[OpenCV](https://opencv.org/), [Pillow](https://python-pillow.org/) and
[pygrabber](https://github.com/andreaschiavinato/python_grabber). See `THIRD_PARTY_LICENSES.txt`.

Not affiliated with OBS Studio, Microsoft or any other mentioned product.
