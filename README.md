# 灵感录屏工具
![image](https://github.com/jia070310/lingg-Screensy/blob/main/iconic/%E5%B1%8F%E5%B9%95%E6%88%AA%E5%9B%BE%202025-12-20%20130445.png)
一款功能强大、界面友好的屏幕录制工具，支持多种录制模式、音频录制和设备管理。

## 🌟 主要功能

- **多种录制模式**：全屏录制、区域录制、窗口录制
- **音频录制**：支持系统音频和麦克风音频录制
- **设备管理**：自动检测摄像头和麦克风设备
- **实时预览**：录制前实时预览录制区域
- **全局快捷键**：支持自定义全局快捷键控制录制
- **视频格式**：支持MP4、AVI等多种视频格式
- **质量设置**：可自定义录制质量和帧率
- **视频编辑**：基础视频编辑功能

## 🛠️ 技术栈

- **语言**：Python 3.7+
- **GUI框架**：PyQt5
- **视频处理**：OpenCV
- **音频录制**：pyaudiowpatch
- **设备检测**：pycaw
- **快捷键**：pynput
- **编译工具**：PyInstaller
- **安装包制作**：Inno Setup

## 📁 项目结构

```
灵感录屏工具/
├── pixel_perfect.py         # 主程序文件
├── config.json              # 配置文件
├── requirements.txt         # 依赖清单
├── setup.iss                # Inno Setup安装脚本
├── iconic/                  # 图标资源文件夹
│   ├── logo.ico            # 程序图标
│   └── *.png               # 界面图标
├── ffmpeg/                  # FFmpeg工具
│   └── bin/ffmpeg.exe      # FFmpeg可执行文件
├── dist/                   # 编译输出目录
└── build/                  # 编译临时目录
```

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 运行程序

```bash
python pixel_perfect.py
```

## 📦 编译打包教程

### 一、使用PyInstaller编译EXE文件

#### 1. 安装PyInstaller

```bash
pip install pyinstaller
```

#### 2. 生成编译配置文件

```bash
pyinstaller --name="灵感录屏工具" --windowed --onefile --icon="iconic/logo.ico" pixel_perfect.py
```

执行完上述命令后，会生成一个`灵感录屏工具.spec`文件。

#### 3. 修改编译配置（可选）

如果需要自定义更多编译选项，可以编辑`灵感录屏工具.spec`文件：

```python
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None


a = Analysis(
    ['pixel_perfect.py'],
    pathex=[],
    binaries=[],
    datas=[('iconic/*', 'iconic'), ('config.json', '.')],  # 添加资源文件
    hiddenimports=['cv2', 'pyaudiowpatch', 'pycaw'],       # 添加隐藏依赖
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='灵感录屏工具',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # 不显示控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='iconic/logo.ico',  # 设置程序图标
)
```

#### 4. 执行编译

```bash
pyinstaller 灵感录屏工具.spec
```

编译成功后，会在`dist`目录下生成`灵感录屏工具.exe`文件。

### 二、使用Inno Setup创建安装包

#### 1. 下载安装Inno Setup

从[Inno Setup官网](https://jrsoftware.org/isdl.php)下载并安装Inno Setup 6.0或更高版本。

#### 2. 准备安装包资源

确保以下资源已准备好：
- 编译好的`灵感录屏工具.exe`（位于`dist`目录）
- `config.json`配置文件
- `iconic`文件夹（包含所有图标资源）
- `ffmpeg`文件夹（包含FFmpeg工具）
- `license.txt`许可证文件（如果需要）

#### 3. 创建Inno Setup脚本

创建`setup.iss`文件，内容如下：

```ini
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
```

#### 4. 编译安装包

1. 打开Inno Setup Compiler
2. 点击"打开"按钮，选择创建的`setup.iss`文件
3. 点击"编译"按钮，等待编译完成
4. 编译成功后，会在当前目录生成`灵感录屏工具安装程序.exe`文件

## 📖 使用说明

### 1. 录制屏幕

1. 选择录制模式（全屏/区域/窗口）
2. 调整录制区域（如果选择区域录制）
3. 选择音频输入设备
4. 点击"开始录制"按钮或使用快捷键开始录制
5. 录制过程中可以暂停/继续录制
6. 点击"停止录制"按钮或使用快捷键停止录制
7. 选择保存路径保存录制的视频

### 2. 快捷键设置

- 默认开始/暂停录制：`Ctrl + Alt + R`
- 默认停止录制：`Ctrl + Alt + S`

可以在设置中自定义快捷键。

### 3. 质量设置

- 分辨率：可选择原始分辨率或自定义分辨率
- 帧率：默认30fps，可自定义15-60fps
- 比特率：默认8000kbps，可根据需要调整
- 视频格式：默认MP4，可选择其他格式

## ⚙️ 配置说明

配置文件`config.json`包含程序的各种设置：

```json
{
  "resolution": "1920x1080",
  "fps": 30,
  "bitrate": 8000,
  "video_format": "mp4",
  "audio_enabled": true,
  "system_audio_enabled": true,
  "microphone_enabled": false,
  "hotkeys": {
    "start_recording": "ctrl+alt+r",
    "stop_recording": "ctrl+alt+s"
  }
}
```

可以直接编辑配置文件或在程序中通过设置界面修改。

## 📦 安装包说明

### 安装流程

1. 双击`灵感录屏工具安装程序.exe`运行安装向导
2. 阅读并接受许可证协议
3. 选择安装目录（默认：`C:\Program Files\灵感录屏工具`）
4. 选择是否创建桌面快捷方式
5. 点击"安装"按钮开始安装
6. 安装完成后，点击"完成"按钮启动程序

### 卸载说明

1. 通过控制面板或开始菜单中的卸载程序卸载
2. 卸载时只会删除应用程序目录，不会删除FFmpeg工具和环境变量

## 🔧 常见问题

### 1. 无法录制系统音频

- 确保已安装`pyaudiowpatch`依赖
- 确保系统音频服务正常运行
- 检查音频设备设置

### 2. 录制视频无声音

- 检查音频输入设备是否正确选择
- 确保音频录制选项已开启
- 检查系统音量设置

### 3. 程序启动失败

- 确保已安装所有依赖
- 检查Python版本是否符合要求（3.7+）
- 检查系统是否支持PyQt5

### 4. 编译失败

- 确保已安装PyInstaller和Inno Setup
- 检查项目路径是否包含中文或特殊字符
- 确保所有资源文件都存在

## 📄 许可证

本项目采用MIT许可证，详情请查看`license.txt`文件。

## 🤝 贡献

欢迎提交Issue和Pull Request！

## 📧 联系方式

如有问题或建议，请联系：

- Email: 718339650@qq.com
- GitHub: https://github.com/inspiration-soft/screen-recorder

---

**灵感录屏工具** - 让录制更简单！ ✨