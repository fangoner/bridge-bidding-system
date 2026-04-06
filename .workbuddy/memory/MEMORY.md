# 项目长期记忆

## 桥牌叫牌练习系统

### 项目基本信息
- **当前版本**：v1.23
- **类型**：基于 AI 的桥牌叫牌练习工具，从 Dify 工作流演进
- **叫牌约定**：JF 叫牌约定（自然叫牌二盖一变种）
- **知识库文件**：`JF实战_标准自然 - Rev 3.2.docx`（项目根目录）

### 技术架构
- **后端**：FastAPI（port:8003），`api/main.py`
- **前端**：React 19 + Material-UI v7 + Vite（port:5173），`web/`
- **AI**：DeepSeek API（叫牌决策）+ 豆包视觉 API（截图识别）
- **分析工具**：Deep Finesse 2014 v2（外部 exe）+ endplay 库

### 核心模块
- `bridge/dealer.py`：发牌，HCP 计算，Fisher-Yates 洗牌
- `bridge/bidding.py`：叫牌序列解析，`extract_retrieval_keyword()` 关键词提取（最复杂逻辑）
- `bridge/bidding_service.py`：AI 叫牌服务，主/备用提示词双轨制
- `bridge/output_format.py`：程序化生成三种输出格式（图形/紧凑/DF）
- `knowledge/loader.py`：JF 约定 RAG 系统，树状结构预处理，精确关键词匹配
- `llm/deepseek_client.py`：DeepSeek API 客户端，JSON Schema 约束输出
- `llm/doubao_client.py`：豆包视觉 API 客户端
- `llm/prompts.py`：主提示词/备用提示词/人类叫牌提示词

### 关键设计
1. **RAG+树状预处理**：JF 约定按双空行分片，精确关键词匹配后解析 `│----` 缩进，提取当前轮次可选叫品注入提示词
2. **双轨提示词**：主提示词（temp=0.2，严格按 JF，无合格叫品输出 `JF无合格叫品`）→ 自动切换备用提示词（temp=0.5，自然推理，保证有效输出）
3. **禁止暴露实际手牌**：提示词规定只引用约定范围，不得透露实际点力/张数
4. **CLI+Web 共享核心**：`main.py` 和 `api/main.py` 共用 `bridge/`、`knowledge/`、`llm/`

### 配置
- API 密钥存 `.env` 文件（DEEPSEEK_API_KEY，DOUBAO_API_KEY 等）
- 默认发牌模式：`DEFAULT_DEAL_SYSTEM = "2D/2H/2S：自然阻击"`
- 主提示词温度：0.2；备用提示词温度：0.5

### 打包分发
- PyInstaller + Inno Setup（Windows 安装包）
- 脚本：`build.bat`，`build_release.bat`

### 历史记录存储（2026-03-26更新）
- **存储位置**：`bidding_history.json`（项目根目录）
- **共享方式**：CLI 和 Web 共用同一文件
- **叫牌序列格式**：字符串 `"(南)1NT-(西)pass-(北)2C-(东)pass-"`
- **Web端访问**：通过 `/api/records` 系列接口
- **数据迁移**：Web端启动时自动迁移 localStorage 旧记录

### Git 状态（2026-03-28更新）
- 当前分支：main
- 完成：右侧面板合并重构（桌面版+手机版）
- 面板切换逻辑：人类回合→叫牌控制+JF约定；AI回合/结束/观察者→叫牌细节
- BiddingControls 新增 `hideJFPanel` prop
- 手机端 `biddingControls` 面板已合并到 `biddingDetails`，前者 return null
- 显示控制选项位置调整：显示AI手牌/队友手牌/AI叫牌输出 checkbox 移至"当前牌局"顶端，与显示小房子 switch 同一排（桌面版+手机版）

### 设置面板重构（2026-03-28更新）
- 设置面板分为"叫牌设置"和"发牌设置"两组，竖线分隔
- 按钮样式统一：字体0.875rem、边框颜色、高度40px
- 图片发牌改为文件上传方式，添加"浏览..."按钮
- 依赖新增：`python-multipart` 包用于文件上传
