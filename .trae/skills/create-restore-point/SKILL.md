---
name: "create-restore-point"
description: "Creates a backup restore point before major changes. Invoke when user asks to create backup, save checkpoint, or before risky modifications."
---

# Create Restore Point Skill

When invoked, this skill creates a backup of the current codebase state.

## Backup Location

- `backups/backup_YYYYMMDD_HHMMSS/` - Timestamped backup folder

## Process

1. **Create backup folder**:
   - Name format: `backup_YYYYMMDD_HHMMSS`
   - Location: `backups/` directory
   - Example: `backups/backup_20260308_234500`

2. **Copy key files and directories**:

   **终端（后端）文件:**
   - `main.py`
   - `config.py`
   - `api/` directory (API接口)
   - `bridge/` directory (桥牌逻辑)
   - `knowledge/` directory (知识库)
   - `llm/` directory (LLM调用)
   - `utils/` directory (工具函数)
   
   **网页（前端）文件:**
   - `web/src/` directory (所有React组件和样式)
   - `web/public/` directory (静态资源)
   - `web/package.json`
   - `web/vite.config.js`
   - `web/index.html`
   
   **文档和配置:**
   - `CHANGELOG.md`
   - `DEVELOPMENT.md`
   - `CLAUDE.md`
   - `JF实战_标准自然 - Rev 3.2.docx` (JF约定文档)
   - `.trae/skills/` directory (所有skill定义)

3. **Report backup summary**:
   - Backup location
   - Files copied
   - Total size

## Example Output

```
创建恢复点
==========

备份位置: backups/backup_20260308_234500/

已备份文件:

终端（后端）:
- main.py
- config.py
- api/ (2 files)
- bridge/ (5 files)
- knowledge/ (1 file)
- llm/ (3 files)
- utils/ (2 files)

网页（前端）:
- web/src/ (15 files)
- web/public/ (2 files)
- web/package.json
- web/vite.config.js
- web/index.html

文档和配置:
- CHANGELOG.md
- DEVELOPMENT.md
- CLAUDE.md
- JF实战_标准自然 - Rev 3.2.docx
- .trae/skills/ (5 files)

恢复点创建成功！
```

## Usage

User: "创建恢复点"
User: "备份一下"
User: "保存当前状态"
User: "我要做大改动，先备份"

## Restore

To restore from a backup:
```
Copy files from backups/backup_YYYYMMDD_HHMMSS/ back to project root
```

## Existing Backups

```
backups/
├── backup_20260221_003319/
├── backup_20260222_021225/
├── backup_20260223_205947/
├── backup_20260226_233544/
├── backup_20260227_120000/
├── backup_20260227_123000/
├── backup_20260301/
├── backup_20260306_222334/
├── backup_20260310_000412/
├── backup_20260321_020337/
└── backup_v1.8.1/
```

## Notes

- All backups are stored in `backups/` directory
- Backup folder is excluded from git (if .gitignore includes backups/)
- Does not backup: __pycache__, .env, node_modules, venv, dist, build
- Keep only recent backups to save disk space
- Consider deleting old backups periodically
- **重要**: 备份包含终端（后端）和网页（前端）所有关键文件，可完整恢复项目
