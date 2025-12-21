; 灵感录屏工具安装脚本
; Inno Setup 6.0 或更高版本

[Setup]
; 基本配置
AppName=灵感录屏工具
AppVersion=1.0
AppPublisher=灵感软件
DefaultDirName={pf}\灵感录屏工具
DefaultGroupName=灵感录屏工具
LicenseFile=license.txt
OutputDir=.
OutputBaseFilename=灵感录屏工具安装程序
SetupIconFile=iconic/logo.ico
Compression=lzma2
SolidCompression=yes

[Languages]
Name: "SChinese"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
; 主程序文件
Source: "dist\灵感录屏工具.exe"; DestDir: "{app}"; Flags: ignoreversion

; 配置文件
Source: "config.json"; DestDir: "{app}"; Flags: ignoreversion

; iconic文件夹中的所有文件
Source: "iconic\*"; DestDir: "{app}\iconic"; Flags: ignoreversion recursesubdirs createallsubdirs

; ffmpeg文件夹
Source: "ffmpeg\*"; DestDir: "C:\ffmpeg"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; 开始菜单图标
Name: "{group}\灵感录屏工具"; Filename: "{app}\灵感录屏工具.exe"; IconFilename: "{app}\iconic\logo.ico"

; 桌面图标
Name: "{commondesktop}\灵感录屏工具"; Filename: "{app}\灵感录屏工具.exe"; IconFilename: "{app}\iconic\logo.ico"; Tasks: desktopicon

[Registry]
; 应用程序卸载信息
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\灵感录屏工具"; ValueType: string; ValueName: "DisplayName"; ValueData: "灵感录屏工具"
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\灵感录屏工具"; ValueType: string; ValueName: "DisplayVersion"; ValueData: "1.0"
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\灵感录屏工具"; ValueType: string; ValueName: "Publisher"; ValueData: "灵感软件"
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\灵感录屏工具"; ValueType: string; ValueName: "UninstallString"; ValueData: "{uninstallexe}"
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\灵感录屏工具"; ValueType: string; ValueName: "DisplayIcon"; ValueData: "{app}\iconic\logo.ico"
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\灵感录屏工具"; ValueType: dword; ValueName: "NoModify"; ValueData: 1
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\灵感录屏工具"; ValueType: dword; ValueName: "NoRepair"; ValueData: 1

[Run]
Filename: "{app}\灵感录屏工具.exe"; Description: "{cm:LaunchProgram,灵感录屏工具}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 仅删除应用程序目录，不删除ffmpeg
Type: filesandordirs; Name: "{app}"