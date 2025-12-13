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

