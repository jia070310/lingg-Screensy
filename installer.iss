#define MyAppName "灵感录屏工具"
#define MyAppVersion "1.0"
#define MyAppPublisher "灵感录屏工具"
#define MyAppExeName "灵感录屏工具.exe"
[Setup]
; 应用程序信息
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=
OutputDir=dist
OutputBaseFilename=灵感录屏工具安装程序
SetupIconFile=iconic\logo.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoDescription={#MyAppName} 安装程序
VersionInfoCopyright=Copyright (C) 2024

; 使用默认英文界面（Inno Setup 6 可能不包含中文语言文件）
[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 6.1

[Files]
; 主程序文件
Source: "dist\灵感录屏工具.exe"; DestDir: "{app}"; Flags: ignoreversion
; iconic文件夹
Source: "iconic\*"; DestDir: "{app}\iconic"; Flags: ignoreversion recursesubdirs createallsubdirs
; ffmpeg文件夹（用于检测和安装）
Source: "ffmpeg\*"; DestDir: "{tmp}\ffmpeg_install"; Flags: ignoreversion recursesubdirs createallsubdirs; Check: ShouldInstallFFmpeg

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\iconic\logo.ico"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"; IconFilename: "{app}\iconic\logo.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\iconic\logo.ico"
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: quicklaunchicon; IconFilename: "{app}\iconic\logo.ico"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 明确不删除FFmpeg相关文件和目录
; 卸载时只删除应用程序文件，不删除C:\ffmpeg

[Code]
var
  FFmpegInstalled: Boolean;
  EnvVarSet: Boolean;

// 检测FFmpeg是否已安装
function IsFFmpegInstalled(): Boolean;
var
  PathValue: String;
begin
  Result := False;
  // 检查系统PATH环境变量
  if RegQueryStringValue(HKEY_LOCAL_MACHINE, 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment', 'Path', PathValue) then
  begin
    if Pos('ffmpeg', LowerCase(PathValue)) > 0 then
    begin
      Result := True;
      Exit;
    end;
  end;
  // 检查用户PATH环境变量
  if RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', PathValue) then
  begin
    if Pos('ffmpeg', LowerCase(PathValue)) > 0 then
    begin
      Result := True;
      Exit;
    end;
  end;
  // 检查C:\ffmpeg\bin是否存在
  if DirExists('C:\ffmpeg\bin') then
  begin
    Result := True;
    Exit;
  end;
end;

// 判断是否需要安装FFmpeg
function ShouldInstallFFmpeg(): Boolean;
begin
  Result := not IsFFmpegInstalled();
  FFmpegInstalled := not Result;
end;

// 设置环境变量
procedure SetEnvironmentVariable(VarValue: String; IsSystem: Boolean);
var
  RootKey: Integer;
  KeyPath: String;
  CurrentValue: String;
  NewValue: String;
begin
  if IsSystem then
  begin
    RootKey := HKEY_LOCAL_MACHINE;
    KeyPath := 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment';
  end
  else
  begin
    RootKey := HKEY_CURRENT_USER;
    KeyPath := 'Environment';
  end;
  
  // 读取当前PATH值
  if RegQueryStringValue(RootKey, KeyPath, 'Path', CurrentValue) then
  begin
    // 检查是否已包含该路径
    if Pos(VarValue, CurrentValue) = 0 then
    begin
      NewValue := CurrentValue;
      if (Length(NewValue) > 0) and (NewValue[Length(NewValue)] <> ';') then
        NewValue := NewValue + ';';
      NewValue := NewValue + VarValue;
      RegWriteStringValue(RootKey, KeyPath, 'Path', NewValue);
      EnvVarSet := True;
    end;
  end
  else
  begin
    // PATH不存在，直接创建
    RegWriteStringValue(RootKey, KeyPath, 'Path', VarValue);
    EnvVarSet := True;
  end;
end;

// 安装FFmpeg
procedure InstallFFmpeg();
var
  FFmpegPath: String;
  FFmpegBinPath: String;
  ErrorCode: Integer;
  ResultCode: Integer;
begin
  FFmpegPath := 'C:\ffmpeg';
  FFmpegBinPath := FFmpegPath + '\bin';
  
  // 复制ffmpeg文件夹到C盘
  if DirExists(ExpandConstant('{tmp}\ffmpeg_install')) then
  begin
    if not DirExists(FFmpegPath) then
    begin
      if not CreateDir(FFmpegPath) then
      begin
        MsgBox('无法创建FFmpeg目录: ' + FFmpegPath, mbError, MB_OK);
        Exit;
      end;
    end;
    
    // 使用robocopy复制文件（更可靠）
    Exec('robocopy', ExpandConstant('"{tmp}\ffmpeg_install" "' + FFmpegPath + '" /E /NFL /NDL /NJH /NJS /R:3 /W:1'), '', SW_HIDE, ewWaitUntilTerminated, ErrorCode);
    
    // robocopy返回码：0-7都是成功
    if (ErrorCode >= 0) and (ErrorCode <= 7) then
    begin
      // 设置系统环境变量
      SetEnvironmentVariable(FFmpegBinPath, True);
      // 设置用户环境变量
      SetEnvironmentVariable(FFmpegBinPath, False);
      
      // 注意：环境变量更改需要重启后才能生效
      // 代码后面会询问用户是否重启
    end
    else
    begin
      MsgBox('安装FFmpeg时出错，错误代码: ' + IntToStr(ErrorCode), mbError, MB_OK);
    end;
  end;
end;

// 初始化安装
procedure InitializeSetup();
begin
  FFmpegInstalled := IsFFmpegInstalled();
  EnvVarSet := False;
end;

// 安装步骤完成后
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    // 如果需要安装FFmpeg
    if not FFmpegInstalled then
    begin
      InstallFFmpeg();
      
      // 如果设置了环境变量，询问是否重启
      if EnvVarSet then
      begin
        if MsgBox('环境变量已设置，需要重启计算机才能生效。' + #13#10 + '是否立即重启计算机？', mbConfirmation, MB_YESNO) = IDYES then
        begin
          Exec('shutdown', '/r /t 0', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
        end;
      end;
    end;
  end;
end;

// 卸载时不删除FFmpeg相关
function InitializeUninstall(): Boolean;
begin
  Result := True;
end;
