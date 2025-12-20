# 灵感录屏工具
![image](https://github.com/jia070310/lingg-Screensy/blob/main/iconic/%E5%B1%8F%E5%B9%95%E6%88%AA%E5%9B%BE%202025-12-20%20130445.png)
一个功能强大、界面美观的 Windows 屏幕录制工具，基于 PyQt5 和 FFmpeg 开发，支持区域录制、音频录制、摄像头录制等功能。

## ✨ 主要特性

### 🎥 录制功能
- **区域选择录制**：支持自由选择屏幕录制区域，支持实时调整录制范围
- **全屏录制**：支持录制整个屏幕
- **窗口录制**：支持选择特定窗口进行录制
- **摄像头录制**：支持摄像头画面叠加到录屏视频中
- **实时预览**：摄像头画面实时预览，可拖拽调整位置

### 🔊 音频功能
- **系统音频录制**：使用 `pyaudiowpatch` 录制系统声音
- **麦克风录制**：支持麦克风音频单独录制和混合
- **音频设备选择**：自动检测并支持选择音频输入/输出设备
- **音频质量设置**：支持无损、高、中、低四种音频质量
- **动态控制**：录制过程中可动态静音/取消静音麦克风

### ⚙️ 高级功能
- **视频质量调节**：支持原画质、高质量、中等质量、低质量四种预设
- **帧率设置**：支持 15/24/30/60 FPS 等多种帧率
- **格式支持**：支持 MP4、AVI、MKV 等多种视频格式
- **暂停/继续**：录制过程中可随时暂停和继续
- **鼠标指针**：可选择是否在录制视频中显示鼠标指针
- **快捷键支持**：支持全局快捷键快速开始/停止录制

### 🎨 界面特性
- **现代化 UI**：圆角设计、深色主题，界面美观
- **无边框窗口**：窗口样式简洁，支持拖拽移动
- **响应式布局**：界面布局合理，操作便捷

### 📁 文件管理
- **视频列表**：自动保存录制历史，方便查看和管理
- **文件命名**：支持自定义文件名模板
- **保存位置**：可自定义视频保存目录

## 📋 系统要求

- **操作系统**：Windows 10/11
- **Python 版本**：3.8 或更高版本（开发环境）
- **FFmpeg**：需要安装 FFmpeg 并添加到系统 PATH 环境变量

## 🚀 安装方法

### 方式一：使用安装程序（推荐）

1. 下载并运行 `灵感录屏工具安装程序.exe`
2. 按照安装向导完成安装
3. 安装程序会自动安装 FFmpeg 到 `C:\ffmpeg` 并配置环境变量
4. 安装完成后，从开始菜单或桌面快捷方式启动程序

### 方式二：从源码运行

1. **克隆或下载项目**
   ```bash
   git clone <repository-url>
   cd 录屏
   ```

2. **安装 Python 依赖**
   ```bash
   pip install -r requirements.txt
   ```

3. **安装 FFmpeg**
   - 下载 FFmpeg：https://ffmpeg.org/download.html
   - 解压到任意目录（推荐 `C:\ffmpeg`）
   - 将 `bin` 目录添加到系统 PATH 环境变量
   - 验证安装：在命令行运行 `ffmpeg -version`

4. **运行程序**
   ```bash
   python pixel_perfect.py
   ```

### 方式三：使用编译好的可执行文件

直接运行 `dist\灵感录屏工具.exe`，无需安装 Python 环境。

## 📦 依赖说明

| 依赖包 | 用途 | 必需性 |
|--------|------|--------|
| PyQt5 | GUI 界面框架 | ✅ 必需 |
| opencv-python | 摄像头画面捕获 | ✅ 必需 |
| pycaw | 音频设备检测 | ⚠️ 可选（用于设备检测） |
| pyaudiowpatch | 系统音频录制 | ⚠️ 可选（用于系统音频录制） |
| pynput | 全局快捷键支持 | ⚠️ 可选（用于快捷键功能） |
| pyinstaller | 打包为可执行文件 | ⚠️ 仅打包时需要 |

**注意**：
- 如果未安装 `pyaudiowpatch`，将无法录制系统音频
- 如果未安装 `pynput`，将无法使用全局快捷键功能
- 如果未安装 `pycaw`，音频设备检测功能可能受限

## 🎮 使用指南

### 基本录制流程

1. **启动程序**
   - 双击运行 `灵感录屏工具.exe`
   - 主界面显示录制控制按钮

2. **选择录制区域**
   - 点击"开始录制"按钮
   - 使用鼠标拖拽选择录制区域
   - 可通过拖拽边缘调整区域大小
   - 确认后开始录制

3. **录制控制**
   - **暂停**：点击暂停按钮或使用快捷键暂停录制
   - **继续**：点击继续按钮恢复录制
   - **停止**：点击停止按钮结束录制

4. **查看录制文件**
   - 录制完成后，视频自动保存到设置的目录
   - 点击"文件列表"按钮查看所有录制历史

### 高级设置

1. **打开设置界面**
   - 点击主界面右上角的设置按钮
   - 或使用快捷键（如果已设置）

2. **视频设置**
   - **质量**：选择视频质量（原画质/高质量/中等质量/低质量）
   - **帧率**：选择录制帧率（15/24/30/60 FPS）
   - **格式**：选择输出视频格式（MP4/AVI/MKV 等）
   - **显示鼠标**：是否在录制视频中显示鼠标指针

3. **音频设置**
   - **系统音频**：启用/禁用系统音频录制
   - **麦克风**：启用/禁用麦克风录制
   - **音频质量**：选择音频质量（无损/高/中/低）
   - **设备选择**：选择音频输入/输出设备

4. **摄像头设置**
   - **启用摄像头**：在录制时叠加摄像头画面
   - **摄像头选择**：选择摄像头设备
   - **预览窗口**：调整摄像头预览窗口位置

5. **快捷键设置**
   - 自定义开始/停止录制的全局快捷键
   - 快捷键可在任何应用程序中使用

### 录制技巧

- **区域调整**：录制过程中可以暂停，然后重新选择区域继续录制
- **音频控制**：录制过程中可通过界面按钮动态控制麦克风静音
- **摄像头位置**：摄像头预览窗口可以拖拽到任意位置
- **文件命名**：在设置中可自定义视频文件命名规则

## 🔧 编译打包

### 本地编译

1. **编译 EXE 文件**
   ```bash
   pyinstaller build_exe.spec --clean --noconfirm
   ```

2. **打包安装程序**
   ```bash
   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
   ```

   安装程序将生成在 `dist` 目录下，文件名为 `灵感录屏工具安装程序.exe`

### GitHub Actions 自动编译

项目已配置 GitHub Actions 工作流，支持自动编译打包：

1. 推送到 `main` 或 `master` 分支
2. 创建针对主分支的 Pull Request
3. 手动触发工作流（在 Actions 页面）

构建完成后，可在 Actions 页面的 Artifacts 中下载安装程序。

详细说明请参考 [BUILD_README.md](BUILD_README.md)

## 🐛 常见问题

### Q: 录制没有声音？
A: 
- 检查是否启用了系统音频或麦克风录制
- 确认音频设备选择正确
- 确保已安装 `pyaudiowpatch`（用于系统音频）

### Q: 找不到 FFmpeg？
A:
- 确认 FFmpeg 已正确安装并添加到 PATH 环境变量
- 在命令行运行 `ffmpeg -version` 验证安装
- 如果使用安装程序，FFmpeg 会自动安装到 `C:\ffmpeg`

### Q: 摄像头无法使用？
A:
- 检查摄像头是否被其他程序占用
- 确认摄像头权限已授予
- 尝试在设置中重新选择摄像头设备

### Q: 快捷键不工作？
A:
- 确认已安装 `pynput` 库
- 检查快捷键是否与其他程序冲突
- 尝试重新设置快捷键

### Q: 录制文件太大？
A:
- 在设置中降低视频质量或帧率
- 使用 MP4 格式（通常文件更小）
- 考虑使用中等或低质量预设

## 📝 开发说明

### 项目结构

```
录屏/
├── pixel_perfect.py      # 主程序文件
├── requirements.txt      # Python 依赖列表
├── build_exe.spec       # PyInstaller 打包配置
├── installer.iss        # Inno Setup 安装程序脚本
├── config.json          # 配置文件（可选）
├── iconic/              # 图标资源文件夹
│   ├── logo.ico        # 程序图标
│   └── *.png           # 各种界面图标
├── ffmpeg/              # FFmpeg 资源文件夹
│   └── bin/
│       └── ffmpeg.exe  # FFmpeg 可执行文件
└── dist/                # 编译输出目录
    ├── 灵感录屏工具.exe
    └── 灵感录屏工具安装程序.exe
```

### 主要模块

- `TruePixelPerfectUI`：主窗口类，负责界面和主要逻辑
- `RegionSelectorWindow`：区域选择窗口
- `RecordingThread`：录制线程，使用 FFmpeg 进行录制
- `SystemAudioRecorder`：系统音频录制器
- `MicrophoneAudioRecorder`：麦克风音频录制器
- `CameraPreviewWindow`：摄像头预览窗口
- `SettingsWindow`：设置窗口
- `FileListWindow`：文件列表窗口

### 技术架构

- **GUI 框架**：PyQt5
- **视频录制**：FFmpeg（通过 subprocess 调用）
- **音频录制**：pyaudiowpatch（系统音频）+ PyAudio（麦克风）
- **摄像头**：OpenCV
- **快捷键**：pynput
- **打包工具**：PyInstaller
- **安装程序**：Inno Setup

## 📄 许可证

请查看 [LICENSE](LICENSE) 文件了解许可证信息。

## 🙏 致谢

- [FFmpeg](https://ffmpeg.org/) - 强大的多媒体处理框架
- [PyQt5](https://www.riverbankcomputing.com/software/pyqt/) - 跨平台 GUI 框架
- [OpenCV](https://opencv.org/) - 计算机视觉库
- [Inno Setup](https://jrsoftware.org/isinfo.php) - Windows 安装程序制作工具

## 📮 反馈与支持

如有问题或建议，欢迎提交 Issue 或 Pull Request。

---

**注意**：本工具仅供学习和个人使用，请遵守相关法律法规，不要用于非法用途。

# 发布说明

本文档说明如何将编译打包完成的产物发布到 GitHub Releases。

## 🚀 自动发布（推荐）

### 方式一：创建 Tag 自动发布

当您创建一个以 `v` 开头的 tag 时，GitHub Actions 会自动编译打包并发布到 Releases。

**步骤：**

1. **创建并推送 tag**
   ```bash
   # 创建 tag（例如 v1.0.0）
   git tag v1.0.0
   
   # 推送 tag 到 GitHub
   git push origin v1.0.0
   ```

2. **等待自动发布**
   - GitHub Actions 会自动检测到 tag 推送
   - 自动触发编译打包流程
   - 编译完成后自动创建 Release 并上传文件

3. **查看 Release**
   - 前往 GitHub 仓库的 Releases 页面
   - 您会看到新创建的 Release，包含：
     - `灵感录屏工具安装程序.exe` - 完整安装程序
     - `灵感录屏工具.exe` - 便携版可执行文件

### Tag 命名规范

建议使用语义化版本号：
- `v1.0.0` - 主版本号.次版本号.修订号
- `v1.0.1` - 修复版本
- `v1.1.0` - 功能更新
- `v2.0.0` - 重大更新

## 📦 手动发布

如果您想手动创建 Release，可以按以下步骤操作：

### 方式一：从 Artifacts 下载后手动上传

1. **触发编译**
   - 前往 GitHub 仓库的 Actions 页面
   - 选择 "编译打包" 工作流
   - 点击 "Run workflow" 手动触发

2. **下载构建产物**
   - 等待编译完成
   - 在 Actions 运行详情页面的 "Artifacts" 部分
   - 下载 "安装程序" artifact

3. **创建 Release**
   - 前往仓库的 Releases 页面
   - 点击 "Draft a new release"
   - 填写 Release 信息：
     - **Tag**: 选择或创建新 tag（如 `v1.0.0`）
     - **Title**: Release 标题（如 `v1.0.0`）
     - **Description**: Release 说明
   - 上传下载的安装程序文件
   - 点击 "Publish release"

### 方式二：使用 GitHub CLI

如果您安装了 GitHub CLI，可以使用命令行创建 Release：

```bash
# 安装 GitHub CLI（如果未安装）
# Windows: winget install GitHub.cli
# 或访问: https://cli.github.com/

# 登录 GitHub
gh auth login

# 创建 Release 并上传文件
gh release create v1.0.0 \
  --title "v1.0.0" \
  --notes "## 更新内容

- 功能更新
- Bug 修复" \
  dist/灵感录屏工具安装程序.exe \
  dist/灵感录屏工具.exe
```

## 📝 Release 说明模板

创建 Release 时，可以使用以下模板：

```markdown
## 📦 安装程序

- **灵感录屏工具安装程序.exe** - 完整安装程序（推荐）
  - 自动安装 FFmpeg 并配置环境变量
  - 包含所有必要的依赖和资源文件
- **灵感录屏工具.exe** - 便携版可执行文件
  - 可直接运行，无需安装
  - 需要手动配置 FFmpeg 环境变量

## 🚀 使用方法

1. 下载并运行 `灵感录屏工具安装程序.exe`（推荐）
2. 按照安装向导完成安装
3. 安装程序会自动安装 FFmpeg 到 `C:\ffmpeg` 并配置环境变量
4. 安装完成后，从开始菜单或桌面快捷方式启动程序

## ✨ 更新内容

### 新增功能
- 功能描述

### 修复问题
- 问题描述

### 改进优化
- 优化描述

## 📋 系统要求

- Windows 10/11
- 需要管理员权限（用于安装 FFmpeg）

## 🔗 相关链接

- [项目主页](https://github.com/your-username/your-repo)
- [问题反馈](https://github.com/your-username/your-repo/issues)
- [使用文档](https://github.com/your-username/your-repo/blob/main/README.md)
```

## ⚙️ 工作流配置说明

当前 GitHub Actions 工作流配置：

- **自动触发**：
  - 推送到 `main` 或 `master` 分支时自动编译
  - 创建以 `v` 开头的 tag 时自动编译并发布

- **手动触发**：
  - 可在 Actions 页面手动触发编译（不自动发布）

- **自动发布**：
  - 仅在创建 tag 时自动发布到 Releases
  - 手动触发不会自动发布（需要手动创建 Release）

## 🔍 检查发布状态

发布完成后，您可以：

1. 前往 Releases 页面查看新创建的 Release
2. 检查文件是否正确上传
3. 测试下载链接是否正常
4. 编辑 Release 说明（如果需要）

## 💡 提示

- 建议在发布前先在本地测试安装程序
- 发布前检查版本号是否正确
- 可以创建预发布版本（Pre-release）用于测试
- 使用语义化版本号便于版本管理

