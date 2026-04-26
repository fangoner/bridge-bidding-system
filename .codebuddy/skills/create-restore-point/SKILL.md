---
name: "create-restore-point"
description: "Create a backup restore point before major changes. This skill should be used when the user asks to create backup, says 备份/保存当前状态/创建恢复点, or before risky modifications. Trigger phrases include: 备份, 创建恢复点, 保存状态, save checkpoint, create backup."
---

# Create Restore Point Skill

## Overview

Create a timestamped backup of critical project files in `backups/` directory. This provides a restore point independent of Git, capturing files that Git may not track (e.g., uncommitted changes, gitignored configs).

## Backup Strategy

1. **Git commit first** if there are uncommitted changes (recommended but not required)
2. **Create timestamped backup** in `backups/backup_YYYYMMDD_HHMMSS/`
3. **Report summary** with backup location, file count, and total size

## Process

### Step 1: Determine backup type

Ask the user for an optional label (e.g., "before_refactor", "v1.37"). If none provided, use timestamp only.

Format: `backups/backup_YYYYMMDD_HHMMSS[_label]/`

### Step 2: Git status check

Run `git log --oneline -1` to get the current commit hash for the backup report.

If there are uncommitted changes, note them in the report but proceed with backup anyway (backup captures working directory state, not just committed state).

### Step 3: Create backup directory

Use PowerShell to create the backup folder:

```powershell
$backupDir = "backups/backup_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
New-Item -ItemType Directory -Path $backupDir -Force
```

### Step 4: Copy files

Copy the following files and directories to the backup folder. Use `Copy-Item -Recurse -Force` for directories.

**Backend:**
- `main.py`
- `config.py`
- `run.py`
- `endplay_integration.py`
- `api/` (entire directory)
- `bridge/` (entire directory)
- `knowledge/` (entire directory)
- `llm/` (entire directory)
- `utils/` (entire directory)
- `tests/` (entire directory)

**Frontend:**
- `web/src/` (entire directory)
- `web/public/` (entire directory)
- `web/package.json`
- `web/vite.config.js`
- `web/index.html`

**Docs & Config:**
- `README.md`
- `CHANGELOG.md`
- `DEVELOPMENT.md`
- `CLAUDE.md`
- `LICENSE.txt`
- `requirements.txt`
- `.gitignore`
- `*.docx` (all docx files, e.g. JF约定文档)

**Skills:**
- `.trae/skills/` (entire directory, preserve Trae skills)
- `.codebuddy/skills/` (entire directory, preserve CodeBuddy skills)

**Scripts & Packaging:**
- `*.bat` (all batch scripts)
- `*.ps1` (all PowerShell scripts)
- `installer.iss`
- `build.spec`

**Case Data:**
- `bidding-cases/` (entire directory)

**Do NOT copy:**
- `__pycache__/`, `node_modules/`, `venv/`, `.venv/`
- `dist/`, `build/`
- `.env` (contains secrets, should be backed up separately)
- `backups/` (avoid recursive backup of backups)
- `*.pyc`, `*.egg-info/`

### Step 5: Report summary

After backup completes, report:
- Backup location (full path)
- Number of files copied
- Total size (human-readable: KB/MB)
- Git commit hash at time of backup
- Any warnings (uncommitted changes, missing files)

### Step 6: Cleanup old backups (optional, ask user)

If `backups/` contains more than 3 backup folders, ask the user if they want to clean up old ones. If yes, keep only the 3 most recent.

## Example Output

```
恢复点创建完成
==============

Git Commit: abc1234 - "Fix bidding logic"
未提交变更: 无

备份位置: backups/backup_20260426_200000/

文件统计:
- 后端: 6 files, 5 directories
- 前端: 15 files, 2 directories
- 文档: 8 files
- 脚本: 12 files
- 案例: 33 files
- Skills: 6 directories

总大小: 2.3 MB
文件总数: 128

备份成功！
```

## Cleanup Command

To clean up old backups (keep the 3 most recent):

```powershell
Get-ChildItem "backups" -Directory | Sort-Object Name -Descending | Select-Object -Skip 3 | Remove-Item -Recurse -Force
```

## Notes

- Backups are gitignored (via `.gitignore` line `backups/`)
- Backups are stored in the project root `backups/` directory
- Each backup is a standalone snapshot, not incremental
- Recommended to keep no more than 3-5 recent backups to save disk space
- This complements Git: Git tracks committed history, backups protect working directory state
