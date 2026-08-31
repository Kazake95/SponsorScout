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

; Natively detect if SponsorScout is already running
AppMutex=SponsorScoutAppMutex
; Force-close the app during both install and uninstall
CloseApplications=force
RestartApplications=no

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"

[Files]
; With --onedir PyInstaller build, the entire build directory is copied.
; Recurse into subdirs and create all subdirectories at install time.
Source: "dist\SponsorScout-InstallerFiles\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppIcoName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppIcoName}"; Tasks: desktopicon

[Registry]
; Set PLAYWRIGHT_BROWSERS_PATH to use the bundled _playwright directory
; for offline operation without requiring internet on first run.
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; ValueType: expandsz; ValueName: "PLAYWRIGHT_BROWSERS_PATH"; ValueData: "{app}\_playwright"; Flags: uninsdeletevalue; Permissions: everyone-modify

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
; Clean up installed folders and files that weren't copied by Inno (databases, logs, settings)
Type: filesandordirs; Name: "{app}"
Type: filesandordirs; Name: "{userappdata}\SponsorScout"
Type: filesandordirs; Name: "{localappdata}\ms-playwright"
Type: filesandordirs; Name: "{localappdata}\SponsorScout"
Type: filesandordirs; Name: "{%USERPROFILE}\.sponsorscout"

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
        messagebox.showinfo('Warning', 'Failed to create AppData folder. Database features may be restricted.');
      end;
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  AppDir: string;
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    // Synchronously terminate any running instance of the application at the start of uninstall
    // to prevent file locks or orphaned processes.
    Exec(ExpandConstant('{sys}\taskkill.exe'), '/f /im SponsorScout.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;

  if CurUninstallStep = usPostUninstall then
  begin
    // 1. Recursive cleanup of the AppData user folder (SQLite databases, logs, customized prompts)
    AppDir := GetUserAppDataDir();
    if DirExists(AppDir) then
    begin
      Log('Removing AppData directory: ' + AppDir);
      DelTree(AppDir, True, True, True);
    end;

    // 2. Remove the user profile dot folder (~/.sponsorscout) if it exists
    AppDir := ExpandConstant('{%USERPROFILE}\.sponsorscout');
    if DirExists(AppDir) then
    begin
      Log('Removing user profile dot folder: ' + AppDir);
      DelTree(AppDir, True, True, True);
    end;

    // 3. Remove the Local AppData cache folder ({localappdata}\SponsorScout)
    AppDir := ExpandConstant('{localappdata}\SponsorScout');
    if DirExists(AppDir) then
    begin
      Log('Removing Local AppData folder: ' + AppDir);
      DelTree(AppDir, True, True, True);
    end;

    // 4. Remove Playwright's downloaded browser binaries ({localappdata}\ms-playwright)
    AppDir := ExpandConstant('{localappdata}\ms-playwright');
    if DirExists(AppDir) then
    begin
      Log('Removing Playwright browser binaries: ' + AppDir);
      DelTree(AppDir, True, True, True);
    end;
  end;
end;