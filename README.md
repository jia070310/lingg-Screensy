# 灵感录屏工具

Python + PyQt5 的桌面录屏工具，支持屏幕录制、系统/麦克风音频、摄像头叠加，并提供一键打包成 EXE 和 Inno Setup 安装包的流程。

## 功能特性
- 屏幕录制，支持窗口/区域选择
- 系统音频和麦克风录制，可选摄像头画中画
- 全局快捷键控制开始/暂停/停止
- 自定义保存目录与文件命名规则
- 自动检测/安装 FFmpeg（安装包内置，必要时安装到 C:\ffmpeg 并设置环境变量）
- 安装包默认创建桌面快捷方式，卸载时保留 FFmpeg

## 目录结构
- `pixel_perfect.py` 主程序
- `iconic/` 应用图标与 UI 资源，包含 `logo.ico`
- `ffmpeg/` 内置的 FFmpeg 目录（安装时按需释放到 `C:\ffmpeg`）
- `build_exe.spec` PyInstaller 打包配置
- `installer.iss` Inno Setup 安装脚本
- `.github/workflows/build.yml` GitHub Actions 自动编译/打包
- `BUILD_README.md` 详细的本地/CI 编译说明

## 环境要求
- 操作系统：Windows 10/11
- Python：3.10+（Actions 使用 3.11）
- 依赖：见 `requirements.txt`
- 构建工具：PyInstaller、Inno Setup 6

## 本地运行
```bash
pip install -r requirements.txt
python pixel_perfect.py
```

## 本地打包
1) 生成 EXE  
```bash
pyinstaller build_exe.spec --clean --noconfirm
```
2) 生成安装包  
```bash
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
```
生成产物位于 `dist/`：`灵感录屏工具.exe`、`灵感录屏工具安装程序.exe`。

## GitHub Actions 一键编译
- 推送到 `main/master` 自动触发，或在仓库 Actions 里点 “Run workflow”
- 工作流会：
  1) 安装依赖  
  2) `pyinstaller build_exe.spec --clean --noconfirm`  
  3) 安装 Inno Setup 并执行 `installer.iss`  
  4) 上传产物（安装包 + EXE）到 Artifacts

## 安装包行为
- 默认中文向导，图标使用 `logo.ico`
- 安装时检测系统 FFmpeg：已安装则跳过，未安装则释放到 `C:\ffmpeg` 并写入系统/用户 PATH
- 设置 PATH 后询问是否重启；若未改动环境变量则不提示重启
- 卸载时不删除 `C:\ffmpeg` 及其环境变量
- 默认勾选桌面快捷方式

## 常见问题
- **推送被拒绝**：先执行 `git pull --rebase` 再 `git push`
- **找不到 Inno Setup**：确认路径 `C:\Program Files (x86)\Inno Setup 6\ISCC.exe`
- **EXE 启动缺少 DLL**：确认依赖已安装，建议用 Actions 打包生成的 EXE

## 许可证
遵循 GPL-3.0（与远程仓库一致）。
# lingg-Screensy
灵感录屏工具，可以录制屏幕和音频 麦克风 摄像头
