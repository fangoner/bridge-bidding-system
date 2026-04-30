---
name: "create-restore-point"
description: "Creates a backup restore point before major changes. Invoke when user asks to create backup, save checkpoint, or before risky modifications."
---

# Create Restore Point Skill

When invoked, this skill creates a backup of the current codebase state.

## Version Control Strategy

本项目使用 **Git + 备份** 双重版本控制：

1. **Git**: 日常版本控制，记录每次修改
2. **备份**: 重要节点存档，防止意外丢失

## Backup Location

- `backups/backup_YYYYMMDD_HHMMSS/` - Timestamped backup folder
- 或 `backups/backup_vX.X.X/` - 版本标签备份

## Process

1. **Git提交（推荐先执行）**:
   ```bash
   git add .
   git commit -m "描述本次修改"
   ```

2. **创建备份文件夹**:
   - Name format: `backup_YYYYMMDD_HHMMSS`
   - Location: `backups/` directory
   - Example: `backups/backup_20260308_234500`

3. **Copy ALL files and directories listed below**:

   **⚠️ 强制规则：必须复制以下所有项目，不得遗漏任何一项。不允许只备份"本次修改相关"的文件。备份的目的是完整恢复，不是增量保存。**

   **终端（后端）文件:**
   - `main.py`
   - `config.py`
   - `run.py`
   - `endplay_integration.py`
   - `api/` directory (API接口)
   - `bridge/` directory (桥牌逻辑)
   - `knowledge/` directory (知识库)
   - `llm/` directory (LLM调用)
   - `utils/` directory (工具函数)
   - `tests/` directory (测试文件)
   
   **网页（前端）文件:**
   - `web/src/` directory (所有React组件和样式)
   - `web/public/` directory (静态资源)
   - `web/package.json`
   - `web/vite.config.js`
   - `web/index.html`
   
   **文档和配置:**
   - `README.md`
   - `CHANGELOG.md`
   - `DEVELOPMENT.md`
   - `CLAUDE.md`
   - `LICENSE.txt`
   - `requirements.txt`
   - `.gitignore`
   - `JF实战_标准自然 - Rev 3.2.docx` (JF约定文档)
   - `.trae/skills/` directory (所有skill定义)
   
   **脚本和打包:**
   - `build.bat`, `build_release.bat`
   - `start_web.bat`, `start_backend.bat`, `start_terminal.bat`
   - `update_release.bat`, `update_release.ps1`
   - `fix-terminal.ps1`, `claude-deepseek.bat`
   - `installer.iss`, `build.spec`
   
   **案例数据:**
   - `bidding-cases/` directory (叫牌案例库，包含 case-XXX.json 和 cases-index.json)

4. **验证备份完整性**:
   - 逐项检查上述列表中的每一项是否存在于备份目录中
   - 如果某项在源目录中不存在（如尚未创建的文件），在报告中标注"不存在（已跳过）"
   - 不允许以"本次修改不涉及"为由跳过任何项

5. **Report backup summary**:
   - Backup location
   - 逐项列出所有已备份的文件/目录（按上述分类）
   - 标注跳过的项目及原因
   - Total size
   - Git commit hash (if available)

## Example Output

```
创建恢复点
==========

Git状态: 已提交 (abc1234)

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

### 从Git恢复:
```bash
# 查看历史
git log --oneline

# 恢复到某个版本
git checkout <commit-hash>

# 或回退
git reset --hard <commit-hash>
```

### 从备份恢复:
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
- Backup folder is excluded from git (in .gitignore)
- Does not backup: __pycache__, .env, node_modules, venv, dist, build
- Keep only recent backups to save disk space
- Consider deleting old backups periodically
- **重要**: 
  - Git用于日常版本控制，可回退到任意历史版本
  - 备份用于重要节点存档，双重保险
  - 大改动前建议先Git commit，再创建备份
