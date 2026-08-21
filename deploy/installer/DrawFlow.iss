#ifndef ClientVersion
  #error ClientVersion must be supplied to ISCC.
#endif
#ifndef StageDir
  #error StageDir must be supplied to ISCC.
#endif
#ifndef OutputDir
  #error OutputDir must be supplied to ISCC.
#endif
#ifndef OutputName
  #define OutputName "DrawFlow-Setup"
#endif

[Setup]
AppId={{E02B424F-FE29-4CCB-8C59-DF14F59F6818}
AppName=DrawFlow
AppVersion={#ClientVersion}
AppVerName=DrawFlow {#ClientVersion}
DefaultDirName={localappdata}\Programs\DrawFlow
DefaultGroupName=DrawFlow
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline
OutputDir={#OutputDir}
OutputBaseFilename={#OutputName}
Compression=lzma2
SolidCompression=yes
UninstallDisplayName=DrawFlow
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "{#StageDir}\DrawFlow.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\drawflow-launcher.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\active.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\versions\{#ClientVersion}\*"; DestDir: "{app}\versions\{#ClientVersion}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\DrawFlow"; Filename: "{app}\DrawFlow.exe"
Name: "{autodesktop}\DrawFlow"; Filename: "{app}\DrawFlow.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; Flags: unchecked

[Run]
Filename: "{app}\DrawFlow.exe"; Description: "启动 DrawFlow"; Flags: nowait postinstall skipifsilent
