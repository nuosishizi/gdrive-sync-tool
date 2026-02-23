[Setup]
AppName=Google Drive Sync
AppVersion=1.0.9
DefaultDirName={autopf}\GDriveSync
DefaultGroupName=GDriveSync
UninstallDisplayIcon={app}\GDriveSync.exe
Compression=lzma2
SolidCompression=yes
OutputDir=dist
OutputBaseFilename=GDriveSync-Windows-Setup
SetupIconFile=app_icon.ico
PrivilegesRequired=lowest

[Files]
Source: "dist\GDriveSync\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "app_icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Google Drive Sync"; Filename: "{app}\GDriveSync.exe"; IconFilename: "{app}\app_icon.ico"
Name: "{autodesktop}\Google Drive Sync"; Filename: "{app}\GDriveSync.exe"; IconFilename: "{app}\app_icon.ico"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"; Flags: unchecked

[Run]
Filename: "{app}\GDriveSync.exe"; Description: "Launch Google Drive Sync NOW"; Flags: nowait postinstall skipifsilent
