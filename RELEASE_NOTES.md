Cam Multiplier 1.2.0

## New

- **Stream from link:** choose "Stream from link ..." in the camera list and paste a link. This can be the link
  shown by the LAN Stream plugin of another Cam Multiplier (for example from a second PC), or any http/rtsp
  video stream.
- **Settings per copy:** every virtual camera has a **Settings** button with output frame rate, zoom, rotation,
  brightness and contrast. Mirroring and size are right in the list. Most changes apply while running.
- **Camera settings:** resolution and frame rate of the camera moved to a **Settings** button next to the camera list.
- **Plugins:** extend Cam Multiplier with extra features (**Plugins** button). External plugins go into
  `%APPDATA%\CamMultiplier\plugins` (see `PLUGINS.md`).
- **LAN Stream (built-in plugin):** watch the copies in a browser on another device in the same network, for
  example on a phone. A random access key protects the link.
- **Automatic reconnect:** if the webcam is unplugged or the stream stops, the virtual cameras keep the last
  frame and reconnect as soon as the source is back.
- **Own driver interface:** the `pyvirtualcam` package is no longer needed. The program talks to the Unity Capture
  driver directly.
- **New app icon.**
- **More robust camera setup:** it runs in the background and the program restarts afterwards. Log files are written
  to `%APPDATA%\CamMultiplier\` (`app.log`, `crash.log`).

## Notes

- Windows SmartScreen may warn because the installer is not code-signed: **More info -> Run anyway**.
- Administrator permission is needed once to register the virtual cameras.
- LAN Stream is not encrypted. Use it only in networks you trust. Windows may ask to allow network access the first
  time: choose private networks.
- Close all other programs that use the physical webcam before pressing Start.
- Individual names per virtual camera and more features are in development.
