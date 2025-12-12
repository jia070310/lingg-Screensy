# 编译打包说明

## 本地编译打包

### 1. 编译EXE文件
```bash
pyinstaller build_exe.spec --clean --noconfirm
```

### 2. 打包安装程序
使用Inno Setup编译安装程序：
```bash
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
```

安装程序将生成在 `dist` 目录下，文件名为 `灵感录屏工具安装程序.exe`

## GitHub Actions 自动编译打包

### 使用方法

1. **上传代码到GitHub**
   - 在GitHub上创建新仓库
   - 将代码推送到仓库

2. **手动触发编译打包**
   - 进入GitHub仓库页面
   - 点击 "Actions" 标签
   - 选择 "编译打包" 工作流
   - 点击 "Run workflow" 按钮
   - 选择分支后点击 "Run workflow" 开始编译

3. **下载构建产物**
   - 编译完成后，在 Actions 页面找到对应的运行记录
   - 点击进入详情页
   - 在 "Artifacts" 部分下载 "安装程序"

### 自动触发

工作流会在以下情况自动触发：
- 推送到 `main` 或 `master` 分支
- 创建针对 `main` 或 `master` 分支的 Pull Request

## 安装程序功能

- ✅ 中文安装界面
- ✅ 自动检测FFmpeg是否已安装
- ✅ 未安装FFmpeg时自动安装到C:\ffmpeg并设置环境变量
- ✅ 安装iconic文件夹到程序目录
- ✅ 默认创建桌面快捷方式
- ✅ 卸载时不删除FFmpeg和环境变量
- ✅ 设置环境变量后询问是否重启电脑

## 注意事项

1. 确保 `ffmpeg` 文件夹包含完整的FFmpeg文件
2. 确保 `iconic` 文件夹包含所有图标文件，特别是 `logo.ico`
3. 编译前确保所有依赖已正确安装

