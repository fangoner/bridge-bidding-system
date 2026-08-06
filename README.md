# 桥牌叫牌练习系统

一个基于 AI 的桥牌叫牌与打牌练习工具，支持双人/四人叫牌练习，内置 JF 叫牌约定知识库，并集成多种打牌引擎（DD、MCTS、αμ、LLM 及 DD-αμ-LLM 主力引擎）。

## 功能特点

- 🃏 **双人/四人叫牌模式** - 支持不同位置的叫牌练习
- 🤖 **AI 叫牌决策** - 基于 DeepSeek 大模型 + JF 约定知识库
- 🔍 **约束导向采样** - 按牌型/点力约束生成可能的牌局，支持负向推断与动态收窄
- 🎯 **多引擎打牌** - 集成 DD 蒙地卡罗、MCTS、αμ 搜索、LLM 及主力引擎 DD-αμ-LLM
- 🧠 **LLM 分组审查** - 引擎给出候选后，由 LLM 按战术意图分组复核并制定打牌计划
- 🖼️ **图片识别** - 支持从截图/图片识别牌局（豆包视觉）
- 📊 **Deep Finesse 集成** - 定约可行性双明手分析
- 🕹️ **复盘与历史** - 打牌过程逐墩回放、DD 出牌提示、历史记录保存/载入
- ⚖️ **局况与发牌模式** - 支持局况配置与多种发牌模式
- 📱 **响应式界面** - 支持桌面和移动端

## 打牌引擎

| 引擎 | 说明 |
|------|------|
| **DD-αμ-LLM**（主力） | 中盘 DD 搜索 + 残局 αμ 搜索，均叠加 LLM 分组审查；按剩余牌数分界切换 |
| DD | 蒙地卡罗采样 + 双明手分析 |
| MCTS | 蒙特卡洛树搜索 |
| αμ | 论文实现的 αμ 搜索（OutcomeVector / ParetoFront / Root Cut） |
| LLM | 纯大模型打牌 |
| 完美 DD | 全知双明手最佳出牌（需四家完整手牌） |

## 安装

### 环境要求

- Python 3.8+
- Node.js 18+（用于前端）

### 步骤

1. **克隆仓库**
   ```bash
   git clone https://github.com/fangoner/bridge-bidding-system.git
   cd bridge-bidding-system
   ```

2. **安装后端依赖**
   ```bash
   pip install -r requirements.txt
   ```

3. **安装前端依赖**
   ```bash
   cd web
   npm install
   cd ..
   ```

4. **配置 API 密钥**
   ```bash
   cp .env.example .env
   ```

   编辑 `.env` 文件，填入 API 密钥：
   - `DEEPSEEK_API_KEY`（必需）：AI 叫牌与打牌
   - `DOUBAO_API_KEY` + `DOUBAO_VISION_ENDPOINT`（可选）：图片/截屏识别

## 运行

### Web 界面（推荐）

**终端 1 - 启动后端**（端口 8003）：
```bash
uvicorn api.main:app --host 0.0.0.0 --port 8003
```

**终端 2 - 启动前端**（端口 5173，Vite）：
```bash
cd web
npm run dev
```

打开浏览器访问 http://localhost:5173/

### 命令行（CLI）

```bash
python main.py
```

## 使用说明

### 叫牌模式

| 模式 | 说明 |
|------|------|
| 双人叫牌 | 南北方向或东西方向叫牌 |
| 四人叫牌 | 四家位置轮流叫牌 |

### 主要功能

1. **发牌** - 随机生成一副牌
2. **输入牌局** - 手动输入特定牌局
3. **图片读牌** - 从截图/图片识别牌局
4. **叫牌练习** - 双人/四人叫牌，JF 约定参考
5. **打牌练习** - 多引擎 AI 出牌，逐墩复盘
6. **Deep Finesse 分析** - 分析定约可行性
7. **历史记录** - 管理叫牌/打牌历史

## 获取 API 密钥

1. 访问 [DeepSeek 官网](https://platform.deepseek.com/)
2. 注册账号并登录
3. 在 API Keys 页面创建新的 API 密钥

需要图片识别功能时，还需配置豆包（火山方舟）视觉模型接入点。

## 项目结构

```
bridge-bidding-system/
├── main.py              # CLI 主程序入口
├── config.py            # 配置（引擎、采样、模型等）
├── requirements.txt     # Python 依赖
├── api/                 # FastAPI 后端接口
├── bridge/              # 桥牌逻辑
│   ├── play_service.py  # 打牌服务（多引擎分发）
│   ├── play_engine.py   # 打牌引擎
│   ├── bidding.py       # 叫牌逻辑
│   ├── mcts/            # 搜索算法（DD / MCTS / αμ / 采样）
│   └── dealer.py        # 发牌
├── knowledge/           # JF 约定知识库加载
├── llm/                 # LLM 调用（DeepSeek / 豆包视觉）
├── utils/               # 工具函数
├── web/                 # 前端代码（React + Vite）
│   └── src/
│       ├── components/  # React 组件
│       ├── context/     # 状态管理
│       ├── hooks/       # 业务逻辑钩子
│       └── services/    # API 调用
└── .env.example         # 环境变量模板
```

## 技术栈

- **后端**: Python, FastAPI, Uvicorn
- **前端**: React, Material-UI, Vite
- **AI**: DeepSeek API（叫牌/打牌）、豆包视觉（图片识别）
- **双明手**: Deep Finesse / DDS

## 常见问题

**Q: 提示"API 密钥无效"怎么办？**

A: 请检查 `.env` 文件中的 API 密钥是否正确，确保没有多余的空格或引号。

**Q: 如何查看 AI 的叫牌分析过程？**

A: 在设置中开启"显示完整 LLM 输出"选项。

**Q: 思考模式打牌很慢？**

A: DeepSeek 思考模式会先生成大量推理 token，比快答慢数秒到数十秒，属正常现象。日常练习建议使用快答。

## 许可证

本软件仅供学习和研究使用。