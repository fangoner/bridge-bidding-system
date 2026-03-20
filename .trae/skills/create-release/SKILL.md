---
name: "create-release"
description: "Packages the application for release. Invoke when user asks to build, package, create release, or prepare for distribution."
---

# Create Release Skill

When invoked, this skill packages the application for distribution.

## Release Process

1. **Pre-build checks**:
   - Verify all tests pass
   - Check for uncommitted changes
   - Confirm version number in DEVELOPMENT.md

2. **Build executable**:
   - Run `build.bat` to create EXE with PyInstaller
   - Output: `dist/桥牌叫牌练习.exe`

3. **Update release package**:
   - Run `update_release.bat` to update `release_桥牌叫牌练习/` folder
   - Copies: EXE, JF约定文档, .env.example, README.txt, LICENSE.txt

4. **Create installer** (optional):
   - Compile `installer.iss` with Inno Setup
   - Output: `output/桥牌叫牌练习_setup.exe`

## Release Package Structure

```
release_桥牌叫牌练习/
├── 桥牌叫牌练习.exe           # 主程序
├── JF实战_标准自然 - Rev 3.2.docx  # 约定文档
├── .env.example              # API配置模板
├── README.txt                # 使用说明
├── LICENSE.txt               # 许可协议
└── Deep Finesse 2014 v2/     # 分析工具
```

## Commands

| Step | Command | Description |
|------|---------|-------------|
| Build | `build.bat` | PyInstaller打包 |
| Update | `update_release.bat` | 更新发布包 |
| Installer | Inno Setup | 创建安装程序 |

## Usage

User: "打包发布"
User: "创建发布版本"
User: "build release"
User: "准备发布"

## Notes

- Requires PyInstaller installed: `pip install pyinstaller`
- Requires Inno Setup for installer creation
- Check API key is not included in release
- Verify .env.example is up to date
