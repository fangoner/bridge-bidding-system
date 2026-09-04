# 桥牌叫牌练习系统 — Code Wiki

> 本文档是该仓库的**代码导航与架构参考**（Code Wiki），面向想要理解、修改或扩展代码的开发者。
> 覆盖：整体架构、模块职责、关键类/函数、依赖关系、运行方式。
> 文档基于仓库当前源码（v1.6x 演进体系，主力引擎 `dd_alphamu_llm`）整理。

---

## 1. 项目概述

一个**基于 AI 的桥牌叫牌与打牌练习系统**，支持：

- **叫牌**：双人/四人叫牌，内置 **JF 实战_标准自然约定知识库**（docx 文档 + 树状检索），通过 DeepSeek 大模型决策。
- **打牌**：7 种打牌引擎 —— LLM、MCTS、DD（蒙地卡罗+双明手）、完美 DD、分层 Tiered、αμ（Pareto 搜索）、以及主力引擎 **DD-αμ-LLM**。
- **辅助**：豆包视觉识别截图/图片读取手牌、Deep Finesse 双明手分析定约、历史记录/复盘。

**技术栈**：Python 3.8+ / FastAPI / Uvicorn（后端），React 19 + Vite + Material-UI（前端），DeepSeek / 豆包 Seed 大模型，DDS（ctypes）双明手求解库。

---

## 2. 整体架构

```
┌──────────────────────────── Web 前端 (React + Vite, :5173) ────────────────────────────┐
│  App.jsx ── context(Game/Bidding/Play) ── hooks ── components ── services/api.js(axios) │
└──────────────────────────────────────┬──────────────────────────────────────────────────┘
                                       │ HTTP REST (端口 8003, vite 代理 /api)
┌──────────────────────────── Web 后端 (FastAPI, api/main.py) ───────────────────────────┐
│  /api/deal /api/bid /api/analyze /api/play/* /api/double-dummy /api/records/* ... 25+  │
└───────────────┬──────────────────────────────────────────┬─────────────────────────────┘
                │                                          │
   ┌────────────▼──────────┐                 ┌────────────▼──────────┐
   │  CLI 入口 main.py     │                 │  核心服务层 bridge/    │
   │  (BiddingGame 状态机) │                 │  BiddingService(叫牌)  │
   └───────────────────────┘                 │  PlayService(打牌)     │
                                             │  PlayEngine / PlayState│
                                             └────────────┬──────────┘
        ┌──────────────┬───────────────┬──────────────┬────▼───────────────┐
        │              │               │              │                    │
 ┌──────▼─────┐ ┌──────▼─────┐ ┌───────▼──────┐ ┌─────▼──────┐  ┌─────────▼──────┐
 │ knowledge/ │ │   llm/     │ │ bridge/mcts/ │ │ deep_finesse│  │ utils/ 外部依赖│
 │ JF知识库加载 │ │ DeepSeek/  │ │ MCTS/DD/αμ/ │ │ (exe)       │  │ history/screenshot
 │ 树检索      │ │ 豆包 提示词 │ │ 采样/求解   │ │ output_format│ │                │
 └────────────┘ └────────────┘ └──────────────┘ └─────────────┘  └────────────────┘
```

**两种入口共享同一套核心服务**：

- **CLI**（`main.py` → `BiddingGame`）与 **Web API**（`api/main.py`）都通过 `bridge/bidding_service.py`（叫牌）和 `bridge/play_service.py`（打牌）工作。
- 前端只通过 HTTP 与后端交互，后端封装所有桥牌逻辑与 AI 调用。

---

## 3. 目录结构与模块职责

```
/workspace
├── main.py                  # CLI 入口（菜单式交互，BiddingGame 状态机）
├── config.py                # 全局配置单一来源（模型、引擎、采样、路径、温度）
├── run.py                   # 简单的测试启动脚本
├── api/main.py              # FastAPI Web 后端（~25+ REST 端点）
├── bridge/                  # ★ 核心桥牌逻辑
│   ├── dealer.py            # # 发牌、Hand/HCP、Position/DealMode 枚举
│   ├── bidding.py           # # 叫牌序列解析、关键字提取、结构约定判断
│   ├── bidding_service.py   # # AI 叫牌服务（JF检索 + 主/fallback 提示词切换）
│   ├── play_types.py        # # 打牌数据模型（Card/Contract/Trick/PlayState/枚举）
│   ├── play_engine.py       # # 打牌状态机（跟牌规则、撤销）
│   ├── play_service.py      # # AI 打牌服务（7 引擎分发）
│   ├── play_strategies.py   # # 打牌策略辅助
│   ├── deep_finesse.py      # # Deep Finesse 外部 exe 集成
│   ├── output_format.py     # # 图形/紧凑/DF 三种输出格式（无 LLM 调用）
│   └── mcts/                # # 搜索算法模块（采样 / MCTS / DD / αμ）
│       ├── __init__.py        # 导出 MctsSearch/DealSampler/HeuristicRollout/RandomizedRollout/DDSearch
│       ├── search.py          # MCTS 确定化 + UCT 树搜索
│       ├── dd_search.py       # 纯蒙特卡洛 + DirectDDS 批量求解 + 残局枚举
│       ├── alpha_mu.py        # αμ Pareto 搜索（2019 Cazenave & Ventos）
│       ├── direct_dds.py      # ctypes 直接封装 DDS C 库（~6x 快于 endplay）
│       ├── sampler.py         # DealSampler 均匀采样 + 分层约束校验(L0-L3)
│       ├── rollout.py         # Heuristic/Randomized rollout 快速打满估分
│       ├── constraints.py     # BidConstraint 约束验证（hard/relaxed/voids-only）
│       ├── bid_constraint_library.py # 叫牌序列→点力/牌型约束映射
│       ├── bit_hands.py       # 位级手牌表示（供 DDS 建盘）
│       ├── belief.py          # 工具函数（void 检测、信号证据收集）
│       ├── signals.py         # 防守信号模型（态度/张数/花色偏好）
│       ├── llm_validator.py   # LLM 出牌规则校验（合法牌/极小/小盖大）
│       └── state_utils.py     # 共享工具（手牌克隆、出牌应用、转换）
├── knowledge/loader.py     # JF docx 解析、Tree 构建、后续叫品预处理
├── llm/
│   ├── deepseek_client.py  # DeepSeek OpenAI SDK 客户端（chat/chat_json + thinking）
│   ├── doubao_client.py    # 豆包视觉/Seed 客户端
│   ├── prompts.py          # 叫牌/打牌提示词模板
│   └── xr_prompts.py       # 新睿体系提示词工具
├── utils/
│   ├── history.py          # 叫牌历史 JSON 存取（BiddingRecord/HistoryManager）
│   └── screenshot.py       # MSS 屏幕截图
├── web/                    # ★ React 前端
│   ├── src/App.jsx           # 顶层组件与全局编排
│   ├── src/context/          # Game/Bidding/Play/AIProgress 4 个 Context
│   ├── src/hooks/            # bidding/model/bridge-records/dealing/doubledummy 等 hooks
│   ├── src/components/       # 布局、叫牌表、打牌面板、设置、历史对话框等
│   ├── src/services/api.js   # axios 后端接口封装
│   ├── src/theme/ src/constants/ src/utils/ src/styles/
│   ├── vite.config.js        # 端口5173，/api 代理到 :8003
│   └── package.json
├── tests/                  # 30+ 独立测试脚本（直接 python 运行，非 pytest）
├── docs/                   # 开发研究/方案类 Markdown 报告
├── bidding-cases/          # 叫牌案例 JSON 记录
├── scripts/                # 新睿(xr)体系解析/验证/批量脚本
└── requirements.txt
```

启动脚本：`start_backend.bat` / `start_web.bat` / `start_services.ps1` / `start_terminal.bat` / `start_api.bat`（Windows 一键启动）。

---

## 4. 配置层（config.py）

`config.py` 是**单一配置来源**，模块加载时 `load_dotenv(BASE_DIR/".env", override=True)` 强制 `.env` 优先。

| 分组 | 关键常量 |
|------|---------|
| API/密钥 | `DEEPSEEK_API_KEY/BASE_URL`、`DOUBAO_API_KEY/.../VISION_ENDPOINT` |
| 叫牌体系 | `JF_CONVENTION_FILE`（.docx）、`DEFAULT_DEAL_SYSTEM="自然阻击"` |
| 模型选择 | `DEFAULT_AI_PROVIDER`、`DEFAULT_MAIN_PROMPT_MODEL/FALLBACK_MODEL`、`MAIN_PROMPT_TEMPERATURE=0.2`/`FALLBACK=0.5` |
| 打牌引擎 | `DEFAULT_PLAY_ENGINE="dd_alphamu_llm"`、`MCTS_SEARCH_MODE`、`DD_SCORING_MODE="imp"`、`LEAD_SIGNAL_SCHEME` |
| MCTS | `MCTS_ITERATIONS=5000`、`MCTS_TIME_LIMIT=10`、`MCTS_EXPLORATION_CONSTANT=1.414`、`ROLLOUT_GREEDY_PROB=0.80` |
| DD | `DD_NUM_SAMPLES=200`、`DD_MIN_SAMPLES=15`、`DD_TIME_LIMIT=30`、`DD_ENDGAME_CARD_THRESHOLD=4` |
| αμ | `ALPHA_MU_NUM_WORLDS=20`、`ALPHA_MU_M=2`、`ALPHA_MU_TIME_LIMIT=60`、`ALPHA_MU_ENDGAME_CARDS=8` |
| 主力引擎 | `DD_ALPHAMU_SWITCH_CARDS=8`（残局切 αμ）、`ALPHAMU_LLM_GAP_CAP=0.35`（审查腿门槛） |
| 防守信号 | `SIGNAL_WEIGHT=1.3`、`SIGNAL_PENALTY=0.7`、`SIGNAL_MIN_RANK=8` |
| 边界校验 | `DD_PARTICLES_MIN/MAX`、`MCTS_PARTICLES_MIN/MAX`、`ALPHA_MU_WORLDS_MIN/MAX` |

模型辅助函数：`is_doubao_model()` / `is_reasoning_model()`（`::reasoning` 后缀）/ `get_base_model()` / `expand_model_list()`。

---

## 5. 核心数据模型（bridge/play_types.py）

- **`Suit`** 枚举：♠♥♦♣ / NT。
- **`PlayerRole`**：`HUMAN` / `AI`。
- **`PlayPhase`** 枚举：`LEAD`（首攻）→ `DUMMY_REVEAL`（明手翻牌）→ `PLAYING` → `COMPLETE`。
- **`Card`**：`suit` + `rank`；`rank_value`（按 `RANK_ORDER`）、`suit_order`（按 `SUIT_ORDER`，"10"→"T"）；`to_dict`/`from_str`。
- **`Contract`**：`level` + `suit` + `declarer` + `doubled/redoubled`；`tricks_needed = level + 6`。
- **`Trick`**：`cards[(position,Card)]`、`leader`、`trump`、`is_ai_cards/ai_reasons/ai_risks/dd_hints`；`winner()` 判定赢家（含将吃/跟牌逻辑）。
- **`PlayState`**：完整牌局状态 —— `hands`、`contract`、`dummy`、`tricks/current_trick`、`current_player`、`declarer_tricks/defender_tricks`、`phase`。关键方法：
  - `play_card()`：出牌 + 跟牌校验 + 墩结算 + 赢家轮转。
  - `get_playable_cards()`：可出牌集合（必须跟出领花色）。
  - `undo_last_card()`（递归跨墩撤销）、`set_hand()`（明手整手）、`is_human_turn()`。
  - `__post_init__`：根据定约自动推导 dummy/首攻者。
- 模块级：`parse_hand_to_cards` / `parse_hands_dict`。

> 注意：`bridge/dealer.py` 还有 `Position`（N/E/S/W）与 `DealMode` 枚举，与这里的中文方位 `POSITION_ORDER=["南","西","北","东"]` 不同，转换在具体调用处处理。

---

## 6. 叫牌子系统

### 6.1 叫牌流程

```
发牌(dealer / 手动 / 图片识别)
   → 对每个应叫位置:
       1. 提取检索关键字 (bidding.extract_retrieval_keyword)
       2. JF 检索 + 预处理 (knowledge.loader JFRetriever.retrieve_with_preprocess)
       3. 走主提示词或 fallback 提示词 (llm.deepseek_client)
       4. 合规性校验，非法则追加反馈重试，耗尽回退 fallback
   → 连续三家 pass 结束
   → 输出图形/紧凑/DF 三种格式 + 存历史
```

### 6.2 关键类/函数

**`bridge/dealer.py`**
- `BridgeDealer`：随机发牌、手动输入解析。
- `Hand` dataclass：HCP、牌型分布、展示字符串。
- `Position` / `DealMode`（free/manual/screenshot/DF）枚举。

**`bridge/bidding.py`** — 关键字提取核心
- `extract_retrieval_keyword()`：按叫牌序列 + deal system 映射出 JF 检索关键字；含"下一位叫牌者"视角、结构约定判断（开叫/二盖一 1D-1H/三/四家 1 高花开叫）、连续 pass 检测、敌方干预后的专类提取。

**`bridge/bidding_service.py`** — AI 叫牌编排
- `BiddingService.ai_bid()`（主流程）：按 `bid_system` 分派 XR/JF → 关键字 → `retrieve_with_preprocess` → 判断开叫人 → 格式化后续叫品 → 主提示词。
- 主提示词重试 + 合规性校验；耗尽走 `fallback_bid()`。

**`knowledge/loader.py`** — JF 知识库
- `JFLoader`：加载 .docx、按标题分段。
- `JFRetriever`：关键字匹配、按 `│----` 缩进建树。
- `navigate_tree_by_bids()`：按叫牌序列遍历树（自动跳过开叫根节点）、支持 "/" 拆分并行叫品、单字母推断 3 阶叫品。
- `get_subsequent_bids_from_node()`：提取结构化后续叫品注入 LLM。

**`llm/prompts.py`** — 提示词模板
- `BIDDING_SYSTEM_PROMPT`（主，12 字段）、`BIDDING_FALLBACK_PROMPT`（19 字段）、`HUMAN_BID_PROMPT`、打牌三件套 `PLAY_DECLARER/DEFENDER/COMMON_RULES`。所有提示词禁止泄露实际手牌。

---

## 7. 打牌子系统

### 7.1 七引擎一览

| 引擎标识 | 引擎名 | 原理 | 触发/说明 |
|---------|-------|------|----------|
| `llm` | LLM | 庄家/防守提示词 | 跟踪已出牌、防守信号、将牌肃清检测 |
| `mcts` | MCTS | 确定化采样 + UCT 树 | 迭代自适应缩放 |
| `dd` | DD | 蒙特卡洛采样 + DirectDDS 批量求解 | 3 层打破平局 |
| `perfect` | Perfect DD | 全知双明手单次求解 | 仅发牌练习模式 |
| `tiered` | Tiered | 多引擎自动调度 | 首攻 DD+LLM 融合、中盘 DD、残局枚举 |
| `alphamu` | αμ | Pareto 搜索（Cazenave&Ventos2019） | 解决 strategy fusion 缺陷，残局多步前瞻 |
| `dd_alphamu_llm` | **DD-αμ-LLM(主力)** | 中盘 DD + 残局 αμ，均叠加 LLM 分组审查 | 剩余牌数与 `DD_ALPHAMU_SWITCH_CARDS` 分界 |

### 7.2 关键类/函数

**`bridge/play_service.py`** — AI 打牌编排
- `PlayService.__init__`：持有 `llm_client`，创建 `PlayEngine`，并按需实例化 `MctsSearch` / `DDSearch` / `AlphaMuSearch` 等引擎。
- `get_ai_play()`：按参数（`use_mcts/use_dd/use_perfect/use_alphamu/use_dd_alphamu_llm`）分发到对应引擎，含 DDS 不可用降级。
- `_llm_play()`：构造局面 + 提示词 → `llm_client.chat_play` → 解析出牌 → 规则校验/fallback → 保存候选对比。

**`bridge/play_engine.py`** — 状态机
- `PlayEngine.initialize()` / `get_state()` / `can_play_card()` / `play_card()` 委托 `PlayState`。

**`bridge/mcts/search.py`** — `MctsSearch`
- 单明手 MCTS：每次迭代采样未知手牌 → Selection→Expansion→Simulation→Backpropagation（UCT）；按剩余未知牌自适应迭代数；按 `avg_value` 选牌（庄/守方向不同）。

**`bridge/mcts/dd_search.py`** — `DDSearch`
- 纯蒙特卡洛 + DirectDDS 批量 `solve_all_boards_raw()`；3 层打破平局（显著性差异 → 小牌偏好 → 平均回退）；`search()`（MC）、`search_perfect()`（全知 DD）、残局精确枚举。

**`bridge/mcts/alpha_mu.py`** — `AlphaMuSearch`
- Pareto 搜索，实现 2021 论文 5 项优化（Cut on Win、Maintaining Useful Worlds、World Cuts、Deep Alpha Cut、Empty Entry、Leaf Parallelization）；`OutcomeVector`/`ParetoFront` 数据结构，迭代加深 `M=1..M`，置换表，DirectDDS 位图残局评估。

**`bridge/mcts/sampler.py`** — `DealSampler`
- 均匀采样 + 分层约束校验回退链：`L0(MH修复) → L1(master-soft) → L2(relaxed,50次) → L3(voids-only,20次) → L4(least-violating)`。

**`bridge/mcts/direct_dds.py`** — DirectDDS
- ctypes 封装 DDS C 库：`solve_all_boards_raw()`（Card 版）/ `solve_all_boards_bits()`（位图版），绕过 endplay 转换，约 6x 快。

**`bridge/mcts/rollout.py`** — `HeuristicRollout`（确定性）/ `RandomizedRollout`（随机加权）用于 MCTS 模拟打满。

**`bridge/mcts/constraints.py`** — `BidConstraint`；源分类 `is_hard_source/is_ignored_source`；`validate_hard/validate_relaxed/validate_voids_only`；`compute_sample_violation_score`（仅诊断）。

**`bridge/mcts/signals.py`** — 防守信号（态度/张数/花色偏好），`collect_all_signals()` 收集、`format_partner_signals_for_prompt()` 注入提示词。

**`bridge/mcts/llm_validator.py`** — 规则校验：牌合法 / 第 4 家"能赢却出小" / 第 2 家"小盖大"，失败回退 `_select_best_card`。

**`bridge/mcts/belief.py`** — 仅保留工具：`collect_voids()`（缺门检测）、`collect_signal_evidence()`（提示词注入）。`BeliefTracker` 已删除。

**`bridge/deep_finesse.py`** — 外部 exe 集成；**`bridge/output_format.py`** — 三种展示格式（无 LLM）。

---

## 8. 模块间依赖关系

```
api/main.py ──> BiddingService, PlayService, Hand, BiddingGame(部分),
                 JFRetriever(reload-jf), HistoryManager(records/*), deep_finesse, output_format
main.py(CLI) ──> BiddingGame ──> BiddingService, HistoryManager, bridge.dealer,
                 deep_finesse, read_cards_from_image(screenshot+doubao)
BiddingService ──> bridge.bidding(extract keyword), knowledge.loader(JF检索),
                 llm.deepseek_client/doubao_client, llm.prompts
PlayService ──> PlayEngine, PlayState, mcts/__init__ 导出的 MctsSearch/DDSearch,
                 AlphaMuSearch, mcts.rollout/sampler/signals/llm_validator/belief,
                 llm.deepseek_client, deep_finesse(DDS备选), mcts.direct_dds
mcts 内部：search→sampler+rollout+state_utils；dd_search→sampler+direct_dds+constraints
           +bid_constraint_library+bit_hands；alpha_mu→sampler+direct_dds+bit_hands+constraints
llm.deepseek_client ──> config(模型名), llm.prompts(可选)
web/services/api.js ──> 后端全部 /api 端点（axios）
```

**运行期依赖约定**：
- 后端固定端口 `8003`、前端固定 `5173`（`strictPort: true`），vite 将 `/api` 代理到后端口。
- `.env` 必须存在（`config.py` 模块级加载），AI 密钥缺失则一切 AI 调用失败。
- 主力引擎的 DDS 求解依赖 `bridge/mcts/direct_dds.py` 编译的 DDS C 库；`endplay` 为可选（CLI 批量双明手）。

---

## 9. 运行方式

### 9.1 环境准备

```bash
pip install -r requirements.txt
cd web && npm install && cd ..
cp .env.example .env   # 填入 DEEPSEEK_API_KEY（必需），可选用豆包视觉
```

### 9.2 Web 启动（推荐）

```bash
# 终端1：后端（注意 v1.48+ 不使用 --reload，防频繁改动崩溃）
uvicorn api.main:app --host 0.0.0.0 --port 8003
# 终端2：前端
cd web && npm run dev
```
访问 http://localhost:5173/。Windows 也可直接运行 `start_services.ps1`。

### 9.3 CLI

```bash
python main.py
```
菜单含：发牌/手动/截图读牌、设置、叫牌练习、定约分析（选项 9 需 `pip install endplay`）、历史、叫牌序列测试。

### 9.4 测试

- 约 30 个独立脚本在 `tests/`，直接运行：`python tests/test_1c_1d.py`（非 pytest）。
- API 测试 `python test_api.py`（需后端运行）。

### 9.5 常用配置文件

| 位置 | 作用 |
|------|------|
| `config.py` | 引擎、采样、模型、温度、路径 |
| `.env` | API 密钥（禁止提交） |
| `JF实战_标准自然 - Rev 3.2.docx` | JF 约定知识库（必须存在于项目根目录） |
| `Deep Finesse 2014 v2/` | 可选外部双明手工具 |

---

## 10. 关键技术备忘（易踩坑点）

- **DeepSeek 思考模式默认关闭**：`thinking` 参数默认 `False`，仅 αμ+LLM"思考模式"显式开启；勿改默认值（思考模式慢 3-5x）。
- **后端勿用 `--reload`**（v1.48+），多文件连续编辑会导致崩溃。
- **叫牌序列格式**：`(S)1H-(W)pass-(N)2C-`（方位前缀 + 叫品，连字符分隔）。
- **同阶花色优先级**：NT > S > H > D > C。
- **`Param` 视角**：关键字提取始终用"下一位叫牌者"视角，而非固定南/北。
- **测试是独立脚本**，无测试框架，`tests/` 文件直接 `python` 执行。