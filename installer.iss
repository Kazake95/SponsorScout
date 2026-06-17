;
; SponsorScout Inno Setup Installer Script
; https://jrsoftware.org/isinfo.php
;
; Production-ready installer:
; - stable AppId
; - no duplicate uninstall registry entry
; - force-close running app during uninstall/install
; - remove AppData user-data folder on uninstall
; - UninstallRun kills SponsorScout.exe before file deletion
;

#define MyAppName      "SponsorScout"
#ifndef MyAppVersion
  #define MyAppVersion "0.1.1"
#endif
#define MyAppPublisher "SponsorScout"
#define MyAppURL       "https://github.com/yourusername/sponsorscout"
#define MyAppExeName   "SponsorScout.exe"
#define MyAppIcoName   "sponsorscout.ico"

[Setup]
AppId=SponsorScout
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
VersionInfoVersion={#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=auto
LicenseFile=LICENSE
OutputDir=dist
OutputBaseFilename=sponsorscout-{#MyAppVersion}-setup
SetupIconFile=sponsorscout\data\sponsorscout.ico
WizardImageFile=sponsorscout\data\sponsorscout.png
WizardSmallImageFile=sponsorscout\data\sponsorscout.png
UninstallDisplayIcon={app}\{#MyAppIcoName}
UninstallDisplayName={#MyAppName}
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
PrivilegesRequired=admin
Compression=lzma2
SolidCompression=yes
ShowTasksTreeLines=yes
DisableFinishedPage=no
; Force-close the app during both install and uninstall
CloseApplications=force
RestartApplications=no
[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"

[Files]
; With --onefile PyInstaller build, only the single .exe and icon need copying.
Source: "dist\SponsorScout-InstallerFiles\SponsorScout.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\SponsorScout-InstallerFiles\sponsorscout.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppIcoName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppIcoName}"; Tasks: desktopicon

[Registry]
; No PLAYWRIGHT_BROWSERS_PATH set — Playwright downloads its browser to
; %LOCALAPPDATA%\ms-playwright automatically on first use.

[Tasks]
Name: "desktopicon"; Description: "Create Desktop Shortcut"; GroupDescription: "Additional Icons"; Flags: unchecked

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

; Kill SponsorScout.exe BEFORE uninstall file deletion begins.
; This ensures the main exe is not locked and can be fully removed.
[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/f /im SponsorScout.exe"; Flags: runhidden runminimized skipifdoesntexist
Filename: "{sys}\taskkill.exe"; Parameters: "/f /im Sponsorscout.exe"; Flags: runhidden runminimized skipifdoesntexist

[UninstallDelete]
; Remove the installed app (.exe + icon)
Type: files; Name: "{app}\*"
; Remove the user data directory (DB, logs, profiles, locale, CV)
Type: filesandordirs; Name: "{userappdata}\SponsorScout"
; Remove any Playwright browser cache downloaded at first run
Type: filesandordirs; Name: "{localappdata}\ms-playwright"
; Remove any SponsorScout data in local app data
Type: filesandordirs; Name: "{localappdata}\SponsorScout"

[Code]
const
  AppDataDirName = 'SponsorScout';

function GetUserAppDataDir(): string;
begin
  Result := ExpandConstant('{userappdata}\' + AppDataDirName);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  AppDir: string;
begin
  if CurStep = ssPostInstall then
  begin
    AppDir := GetUserAppDataDir();
    if not DirExists(AppDir) then
    begin
      if CreateDir(AppDir) then
      begin
        Log('Created AppData dir: ' + AppDir);
        SaveStringToFile(AppDir + '\.keep', #13#10, False);
      end
      else
      begin
        Log('Failed to create AppData dir: ' + AppDir);
        MsgBox('Warning: Could not create the application data folder.'#13#10 +
               'Some features may not work correctly.'#13#10 +
               'Target: ' + AppDir, mbError, MB_OK);
      end;
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  AppDir: string;
  ResultCode: Integer;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    AppDir := GetUserAppDataDir();
    if DirExists(AppDir) then
    begin
      Log('Removing AppData directory: ' + AppDir);
      DelTree(AppDir, True, True, True);
    end;
  end;
end;
