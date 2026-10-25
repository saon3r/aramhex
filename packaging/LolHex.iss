; Installer for the ARAM: Mayhem overlay. Run packaging/build.ps1, which invokes this script.
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{1107079E-6C48-46FD-938D-04B1C3EA9A72}
AppName=AramHex
AppVersion={#AppVersion}
AppPublisher=saon3r
AppPublisherURL=https://github.com/saon3r/aramhex
AppSupportURL=https://github.com/saon3r/aramhex/issues
AppUpdatesURL=https://github.com/saon3r/aramhex/releases
DefaultDirName={localappdata}\Programs\AramHex
DefaultGroupName=AramHex
; Per-user install: no administrator rights. The uninstall entry lives in HKCU.
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=force
OutputDir=..\build\installer
OutputBaseFilename=AramHex-Setup-{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName=AramHex
UninstallDisplayIcon={app}\AramHex.exe
SetupIconFile=lolhex.ico
LicenseFile=..\LICENSE

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional tasks:"

[Files]
Source: "..\build\dist\AramHex\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Clear the previous program files first. An onedir install merges directories, so
; files that no longer exist would otherwise survive an upgrade.
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{group}\AramHex"; Filename: "{app}\AramHex.exe"
Name: "{group}\Uninstall AramHex"; Filename: "{uninstallexe}"
Name: "{userdesktop}\AramHex"; Filename: "{app}\AramHex.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\AramHex.exe"; Description: "Launch AramHex"; Flags: nowait postinstall skipifsilent
; A silent install reopens the app when it finishes.
Filename: "{app}\AramHex.exe"; Flags: nowait; Check: WizardSilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/c taskkill /im AramHex.exe /f"; Flags: runhidden; RunOnceId: "KillAramHex"
