; Inno Setup script for Cam Multiplier
; Run build.bat first, it builds the program into dist\CamMultiplier.

[Setup]
AppName=Cam Multiplier
AppVersion=1.0
AppPublisher=Thomas
DefaultDirName={autopf}\Cam Multiplier
DefaultGroupName=Cam Multiplier
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputBaseFilename=CamMultiplier-Setup
OutputDir=installer_output
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\CamMultiplier.exe

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "dist\CamMultiplier\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "driver\*"; DestDir: "{app}\driver"; Flags: ignoreversion
Source: "THIRD_PARTY_LICENSES.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Cam Multiplier"; Filename: "{app}\CamMultiplier.exe"
Name: "{autodesktop}\Cam Multiplier"; Filename: "{app}\CamMultiplier.exe"; Tasks: desktopicon

[Run]
; Registers the virtual cameras (3 devices, name "Cam Multiplier"; can be changed later inside the program)
Filename: "{sys}\regsvr32.exe"; Parameters: "/s ""{app}\driver\UnityCaptureFilter64.dll"" ""/i:UnityCaptureDevices=3"" ""/i:UnityCaptureName=Cam Multiplier"""; Flags: runhidden waituntilterminated; StatusMsg: "Setting up virtual cameras ..."
Filename: "{syswow64}\regsvr32.exe"; Parameters: "/s ""{app}\driver\UnityCaptureFilter32.dll"" ""/i:UnityCaptureDevices=3"" ""/i:UnityCaptureName=Cam Multiplier"""; Flags: runhidden waituntilterminated
Filename: "{app}\CamMultiplier.exe"; Description: "Start Cam Multiplier"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\regsvr32.exe"; Parameters: "/s /u ""{app}\driver\UnityCaptureFilter64.dll"""; Flags: runhidden; RunOnceId: "UnregCam64"
Filename: "{syswow64}\regsvr32.exe"; Parameters: "/s /u ""{app}\driver\UnityCaptureFilter32.dll"""; Flags: runhidden; RunOnceId: "UnregCam32"
