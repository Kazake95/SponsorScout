;
; SponsorScout Inno Setup Installer Script
; https://jrsoftware.org/isinfo.php
;
; Build command (called from build_exe.ps1):
;   ISCC.exe /DMyAppVersion=X.X.X "/ODistDir" "\Fsponsorscout-<ver>-setup" installer.iss
;

#define MyAppName      "SponsorScout"
#define MyAppVersion   "0.0.0"
#define MyAppPublisher "SponsorScout"
#define MyAppURL       "https://github.com/yourusername/sponsorscout"
#define MyAppExeName   "SponsorScout.exe"
#define MyAppIcoName   "sponsorscout.ico"

[Setup]
AppId={{{#MyAppName}}
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
; 64-bit only, require admin for Program Files + per-machine registry entries
ArchitecturesInstallIn64BitMode=x64
ArchitecturesAllowed=x64
PrivilegesRequired=admin
Compression=lzma2
SolidCompression=yes
; Better progress indicator for large directories
ShowTasksTreeLines=yes
; Always show the wizard (no silent install by default)
DisableFinishedPage=no

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"

; ---------------------------------------------------------------------------
; Files section — copies the built onedir tree into {app}
; The build_exe.ps1 stage creates:
;   dist\SponsorScout-InstallerFiles\  ← our payload
; ---------------------------------------------------------------------------
[Files]
Source: "dist\SponsorScout-InstallerFiles\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs

; ---------------------------------------------------------------------------
; Icons — Start Menu & Desktop shortcuts
; ---------------------------------------------------------------------------
[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppIcoName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppIcoName}"; Tasks: desktopicon

; ---------------------------------------------------------------------------
; Registry — Add/Remove Programs entry + optional UninstallString passthrough
; ---------------------------------------------------------------------------
[Registry]
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppName}"; ValueType: string; ValueName: "DisplayName"; ValueData: "{#MyAppName}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppName}"; ValueType: string; ValueName: "DisplayVersion"; ValueData: "{#MyAppVersion}"
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppName}"; ValueType: string; ValueName: "Publisher"; ValueData: "{#MyAppPublisher}"
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppName}"; ValueType: string; ValueName: "URLInfoAbout"; ValueData: "{#MyAppURL}"
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppName}"; ValueType: string; ValueName: "DisplayIcon"; ValueData: "{app}\{#MyAppIcoName}"
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppName}"; ValueType: string; ValueName: "UninstallString"; ValueData: "\"{uninstallexe}\""; Flags: uninsdeletekey

; ---------------------------------------------------------------------------
; Tasks — Desktop shortcut optional tick-box
; ---------------------------------------------------------------------------
[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopShortCut}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

; ---------------------------------------------------------------------------
; Run — Launch after install
; ---------------------------------------------------------------------------
[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

; ---------------------------------------------------------------------------
; Pascal code for AppData initialisation & complete uninstall cleanup
; ---------------------------------------------------------------------------
[Code]
const
  AppDataDirName = 'SponsorScout';

function GetUserAppDataDir(): string;
begin
  Result := ExpandConstant('{userappdata}\' + AppDataDirName);
end;

function RemoveDirRecursively(DirPath: string): Boolean;
var
  FindRec: TFindRec;
  FullPath: string;
begin
  Result := True;

  if not DirExists(DirPath) then
    Exit;

  if FindFirst(DirPath + '\*', FindRec) then
  begin
    try
      repeat
        if FindRec.Name <> '.' then
          if FindRec.Name <> '..' then
          begin
            FullPath := DirPath + '\' + FindRec.Name;
            if FindRec.Attributes and FILE_ATTRIBUTE_DIRECTORY <> 0 then
            begin
              if not RemoveDirRecursively(FullPath) then
                Result := False;
            end
            else
            begin
              if not DeleteFile(FullPath) then
                Result := False;
            end;
          end;
      until not FindNext(FindRec);
    finally
      FindClose(FindRec);
    end;
  end;

  if not RemoveDir(DirPath) then
    Result := False;
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
        ; Future-proof hint file so Windows Explorer shows the folder
        SaveStringToFile(AppDir + '\.keep', ''#13#10'', False);
      end
      else
      begin
        Log('Failed to create AppData dir: ' + AppDir);
        MsgBox('Warning: Could not create the application data folder.'#13#10 +
               'Some features may not work correctly.'#13#10 +
               'Target: ' + AppDir, mbError, MB_OK);
      end;
    end
    else
    begin
      Log('AppData dir already exists: ' + AppDir);
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  AppDir: string;
begin
  ; On first call (usAppMutexCheck), we only check if the app is running.
  ; The actual cleanup is done in usPostUninstall so the uninstaller
  ; has already removed Program Files, Start Menu, and registry entries.
  if CurUninstallStep = usPostUninstall then
  begin
    AppDir := GetUserAppDataDir();
    if DirExists(AppDir) then
    begin
      Log('Removing AppData directory: ' + AppDir);
      if RemoveDirRecursively(AppDir) then
      begin
        Log('Successfully removed AppData directory.');
      end
      else
      begin
        Log('Warning: Failed to remove AppData directory: ' + AppDir);
        MsgBox('Warning: The uninstaller could not remove all user data.'#13#10 +
               'You may delete the folder manually:'#13#10 + AppDir,
               mbInformation, MB_OK);
      end;
    end
    else
    begin
      Log('No AppData directory found — nothing to clean.');
    end;
  end;
end;
