@echo off
setlocal
title Cam Multiplier - Build
cd /d "%~dp0"
echo.
echo === Cam Multiplier Build ===
echo Ordner: %CD%
echo.

REM --- Dateien pruefen ---
if not exist cam_multiplier.py goto missing_script
if not exist installer.iss goto missing_iss
if not exist THIRD_PARTY_LICENSES.txt goto missing_lic
if not exist cam_multiplier_plugin.py goto missing_plugin
if not exist plugin_lan_stream.py goto missing_plugin
if not exist unitycapture_sender.py goto missing_plugin
if not exist assets\icon.ico goto missing_assets

REM --- Python finden ---
set PY=
where python >nul 2>&1 && set PY=python
if not defined PY where py >nul 2>&1 && set PY=py
if not defined PY goto nopython
echo Python: %PY%

REM --- Treiberdateien von Unity Capture holen, falls nicht vorhanden ---
if not exist driver mkdir driver
if not exist driver\UnityCaptureFilter64.dll powershell -NoProfile -Command "Invoke-WebRequest -UseBasicParsing 'https://raw.githubusercontent.com/schellingb/UnityCapture/master/Install/UnityCaptureFilter64.dll' -OutFile 'driver\UnityCaptureFilter64.dll'"
if not exist driver\UnityCaptureFilter32.dll powershell -NoProfile -Command "Invoke-WebRequest -UseBasicParsing 'https://raw.githubusercontent.com/schellingb/UnityCapture/master/Install/UnityCaptureFilter32.dll' -OutFile 'driver\UnityCaptureFilter32.dll'"
if not exist driver\UnityCaptureFilter64.dll goto nodriver
if not exist driver\UnityCaptureFilter32.dll goto nodriver

REM --- Programm bauen ---
echo.
echo [1/2] Programm wird gebaut ...
%PY% -m pip install --upgrade pyinstaller opencv-python pygrabber pillow
if errorlevel 1 goto fail
%PY% -m PyInstaller --noconfirm --clean --onedir --windowed --name CamMultiplier --icon assets\icon.ico --add-data "assets;assets" --collect-all pygrabber --collect-submodules comtypes cam_multiplier.py
if errorlevel 1 goto fail
if not exist dist\CamMultiplier\CamMultiplier.exe goto fail

REM --- Installer bauen ---
echo.
echo [2/2] Installer wird gebaut ...
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" goto noinno
"%ISCC%" installer.iss
if errorlevel 1 goto fail

echo.
echo FERTIG: %CD%\installer_output\CamMultiplier-Setup.exe
goto end

:missing_script
echo FEHLER: cam_multiplier.py liegt nicht in diesem Ordner.
goto end
:missing_iss
echo FEHLER: installer.iss liegt nicht in diesem Ordner.
goto end
:missing_plugin
echo FEHLER: cam_multiplier_plugin.py, plugin_lan_stream.py oder unitycapture_sender.py liegt nicht in diesem Ordner.
goto end
:missing_assets
echo FEHLER: Der Ordner assets mit icon.ico fehlt.
goto end
:missing_lic
echo FEHLER: THIRD_PARTY_LICENSES.txt liegt nicht in diesem Ordner.
goto end
:nopython
echo FEHLER: Python wurde nicht gefunden. Von python.org installieren und "Add to PATH" anhaken.
goto end
:nodriver
echo FEHLER: Treiberdateien fehlen. Entweder Internet pruefen oder UnityCaptureFilter32.dll und
echo UnityCaptureFilter64.dll aus dem Unity-Capture-Ordner Install nach driver\ kopieren.
goto end
:noinno
echo FEHLER: Inno Setup 6 nicht gefunden. Installieren von jrsoftware.org.
goto end
:fail
echo.
echo FEHLER: Der Build ist fehlgeschlagen. Meldung oben lesen.

:end
echo.
pause
