# 桥牌练习系统 - 开发文档

## 项目概述

本项目是一个桥牌练习工具，从Dify工作流转换为独立应用，支持叫牌和打牌全流程练习。使用JF叫牌约定，通过DeepSeek API（或豆包Seed API）实现AI叫牌/打牌决策，集成Deep Finesse（外部exe）和endplay（Python库）进行双明手分析。

系统包含两大模块：
- **叫牌系统**：双人/四人叫牌练习，JF约定知识库检索，5路径fallback机制
- **打牌系统**：7种打牌引擎（LLM/MCTS/DD/Perfect DD/Tiered/αμ纯引擎/αμ+LLM），αμ搜索解决PIMC缺陷

历史开发文档见 [DEVELOPMENT_HISTORY.md](DEVELOPMENT_HISTORY.md)。

## 系统架构

### 三层架构

```
┌─────────────────────────────────────────┐
│  CLI (main.py)                          │  终端交互
├─────────────────────────────────────────┤
│  Web API (api/main.py, FastAPI)         │  REST API，25+端点
├─────────────────────────────────────────┤
│  Core (bridge/, knowledge/, llm/)       │  核心业务逻辑
└─────────────────────────────────────────┘
```

CLI和Web API共享同一套核心逻辑（`BiddingService` + `PlayService`）。

### 目录结构

```
Bidding System/
├── main.py                 # CLI应用入口
├── api/main.py             # FastAPI Web后端
├── config.py               # 集中配置管理
├── endplay_integration.py  # endplay双明手分析集成
├── .env                    # 环境变量（API密钥）
├── bridge/
│   ├── dealer.py           # 发牌和手牌管理
│   ├── bidding.py          # 叫牌序列解析、关键字提取
│   ├── bidding_service.py  # 叫牌服务（AI/人类叫牌）
│   ├── deep_finesse.py     # Deep Finesse集成
│   ├── output_format.py    # 输出格式生成
│   ├── play_types.py       # 打牌数据类型
│   ├── play_engine.py      # 打牌引擎（规则状态机）
│   ├── play_service.py     # 打牌服务（7种引擎调度）
│   └── mcts/               # 打牌搜索引擎
│       ├── alpha_mu.py     # αμ Pareto搜索引擎
│       ├── belief.py       # 信念工具（void检测/信号证据）
│       ├── bid_constraint_library.py  # 叫牌约束库
│       ├── bit_hands.py    # 位运算手牌表示
│       ├── constraints.py  # BidConstraint约束验证
│       ├── dd_search.py    # DD引擎（蒙特卡洛+DirectDDS）
│       ├── direct_dds.py   # ctypes直接DDS库封装
│       ├── llm_validator.py # LLM出牌校验层
│       ├── rollout.py      # MCTS rollout策略
│       ├── sampler.py      # 手牌采样器
│       ├── search.py       # MCTS搜索引擎
│       ├── signals.py      # 防守信号模型
│       └── state_utils.py  # 共享工具函数
├── knowledge/loader.py     # JF约定文档加载和检索
├── llm/
│   ├── prompts.py          # 提示词模板
│   ├── deepseek_client.py  # DeepSeek客户端
│   └── doubao_client.py    # 豆包视觉/Seed客户端
├── utils/
│   ├── history.py          # 历史记录管理
│   └── screenshot.py       # 截屏功能
└── web/                    # React前端
    └── src/
        ├── App.jsx         # 主应用
        ├── components/     # React组件
        ├── hooks/          # 自定义Hooks
        ├── context/        # Context providers
        ├── services/api.js # API服务层
        ├── utils/          # 前端工具
        ├── theme/          # 主题系统
        └── constants/      # 共享常量
```

## 叫牌系统

### 叫牌流程

叫牌流程核心在 `bridge/bidding_service.py` 的 `ai_bid()` 方法，采用**5路径fallback机制**：

```
ai_bid() 入口
  │
  ├─ 1. 提取关键字 extract_retrieval_keyword()
  ├─ 2. JF检索+预处理 retrieve_with_preprocess()
  │
  ├─ 路径1: jf_content为空（JF片段找不到）
  │   └→ fallback + "成局与满贯"兜底
  │
  ├─ 路径2: 非结构性约定（is_structural=False）
  │   └→ fallback + 原始jf_content
  │
  ├─ 路径3: 无后续叫品（has_subsequent=False）
  │   └→ fallback + "成局与满贯"兜底
  │
  ├─ 路径4: 主提示词返回"JF无合格叫品"
  │   └→ fallback + "成局与满贯"兜底
  │
  ├─ 路径5: 主提示词合规性重试耗尽
  │   └→ fallback + "成局与满贯"兜底
  │
  └─ 主路径: 主提示词返回合格叫品
      └→ 合规性检查通过 → 返回
```

**关键设计**：
- **P0-2修复**：不再设置 `self.use_fallback = True`，每轮独立判断，避免fallback状态跨轮传播
- **主提示词jf_content置空**：主路径只依赖 `subsequent_bids`（预处理结果），不注入原始jf_content避免干扰
- **合规性重试**：主提示词允许 `MAIN_PROMPT_MAX_RETRIES`(2) 次重试，fallback允许 `FALLBACK_PROMPT_MAX_RETRIES`(1) 次重试，重试时附加违规反馈

### 关键字提取

`extract_retrieval_keyword()`（[bridge/bidding.py](bridge/bidding.py)）根据叫牌序列长度和叫品内容提取JF章节关键字。

**视角概念**：视角是序列里下一个待叫的玩家，不是固定为南家。

#### 关键字分类

| 类型 | 示例 | 说明 |
|------|------|------|
| 固定关键字 | `12.1.1 对方加倍后`、`第二家争叫` | 42个固定字符串 |
| 动态开叫 `f"{bid}开叫"` | `1C开叫`、`2NT开叫` | 1C~3NT开叫全覆盖（15个片段） |
| 动态组合 `f"{first}-{third}"` | `1C-1D`、`1NT-2C` | 应叫组合（59个片段） |

#### 关键场景映射（最新）

| 叫牌场景 | 序列示例 | 关键字 |
|---------|---------|--------|
| 开叫（无争叫） | `(南)1C-(西)pass-` | `1C开叫` |
| 1C/1D后对方加倍 | `(南)1C-(西)X-` | `12.1.1 对方加倍后` |
| 1C/1D后对方一阶争叫 | `(南)1C-(西)1H-` | `对方一阶争叫` |
| 1C/1D后对方二阶争叫 | `(南)1C-(西)2H-` | `对方二阶争叫：` |
| 1C/1D后对方高阶争叫 | `(南)1C-(西)3H-` | `JF尚未实现`（兜底） |
| 1H/1S后对方加倍 | `(南)1H-(西)X-` | `12.2.1 敌方加倍` |
| 1H/1S后对方一阶/二阶争叫 | `(南)1H-(西)1S-` | `12.2.2 敌方争叫花色` |
| 1H/1S后对方高阶争叫 | `(南)1H-(西)3S-` | `JF尚未实现`（兜底） |
| 1NT后对方争叫 | `(南)1NT-(西)X-` | `12.3` 或 `12.3.2`（按deal_system） |
| 2NT开叫后无争叫 | `(东)2NT-(南)pass-` | `2NT均型强牌` |
| 2NT开叫后有争叫/应叫 | `(东)2NT-(南)3S-` | `JF尚未实现`（兜底） |

**占位符关键字**（2个，不对应JF片段，走fallback兜底）：
- `JF尚未实现`：2NT开叫后争叫、1C/1D/1H/1S后高阶争叫等JF文档未覆盖场景
- `自然叫牌`：4/5/7叫品的双方参与复杂序列

#### 已废弃关键字

- `我方开叫1低花`：原1C/1D高阶争叫兜底，现改为 `JF尚未实现`
- `我方开叫1高花`：原1H/1S高阶争叫兜底，现改为 `JF尚未实现`

### JF片段索引机制

`knowledge/loader.py` 的 `JFLoader` 加载docx文档，按连续两个空行分段，提取关键字。

**关键字提取规则**（`_extract_keywords` 和 `_build_index`）：
- 前3行作为关键字（标题行）
- 额外识别所有形如 `^\d+\.\d+(\.\d+)*\s` 开头的章节号行作为关键字

JF文档统计：
- 片段总数：127
- 唯一关键字总数：399
- 动态拼接类片段：74个（15个开叫 + 59个组合）

### 提示词系统

#### 三种叫牌提示词

| 提示词 | 用途 | 输出字段 | 触发条件 |
|--------|------|---------|---------|
| `BIDDING_SYSTEM_PROMPT` | 主提示词，结构性约定 | 12个 | 默认 |
| `BIDDING_FALLBACK_PROMPT` | 备用提示词，智能决策 | 19个 | 5路径fallback触发 |
| `HUMAN_BID_PROMPT` | 人类叫牌含义 | - | 人类叫牌时 |

**`{subsequent_bids}` 占位符**：主提示词和人类提示词通过此占位符注入预处理提取的后续叫品列表。fallback提示词不注入预处理结果。

#### 预处理流程

`preprocess_jf_content()`（[knowledge/loader.py](knowledge/loader.py)）：
1. 解析叫牌序列，定位队友最近叫品
2. 在文档内容中找到该叫品的行索引
3. 提取缩进级别+1的后续叫品列表
4. 将后续叫品列表注入提示词

**结构性约定判断**（`is_structural_convention()`）：
- 开叫关键字（如 `1H开叫`、`1NT`、`2C`）
- 双叫品关键字（如 `1D-1H`、`1C-1D`）
- 第三四家开叫1高花（如 `第三四家开叫1H`）
- 其他情况均为非结构性约定

#### 叫品选择优先级

- 开叫位置：优先选择无将（1NT/2NT）
- 非开叫和争叫位置：阶数相同时，高花 > 无将 > 低花
- 花色等级：**S > H > D > C**，NT在同级 outrank S（1NT > 1S）

## 打牌系统

### 引擎架构

打牌系统支持7种引擎，通过 `PlayService.get_ai_play()`（[bridge/play_service.py](bridge/play_service.py)）调度：

| 引擎 | 标志 | 说明 |
|------|------|------|
| LLM | `use_llm`（默认） | DeepSeek API大模型推理 |
| MCTS | `use_mcts` | 确定化 + UCT树搜索 |
| DD | `use_dd` | 纯蒙特卡洛 + DirectDDS双明手评估 |
| Perfect DD | `use_perfect` | 全知双明手，一次solve得所有候选 |
| Tiered | `use_tiered` | 分层自动调度（首攻/中盘/残局） |
| αμ纯引擎 | `use_alphamu` | αμ Pareto搜索，开局到残局全覆盖 |
| αμ+LLM | `use_alphamu_llm` | αμ搜索 + LLM策略审查 |

**引擎选择**：前端 SettingsPanel 下拉框，API `play_engine` 参数控制，或 `DEFAULT_PLAY_ENGINE` 配置。

### αμ搜索引擎

`bridge/mcts/alpha_mu.py` 的 `AlphaMuSearch` 实现 Wbridge5 的 αμ 算法（Cazenave & Ventos 2019），解决 PIMC 的 strategy fusion 和 non-locality 缺陷。

#### 核心数据结构

- **OutcomeVector**：长度 N 的布尔向量（N=possible worlds数量），表示各 world 下庄家方是否成约。支持三态：useful(1/0)、impossible(x=视为1)、useless(-=视为0)
- **ParetoFront**：不被支配的 OutcomeVector 集合，`add()` 自动去支配、`union()` 合并前沿

#### 节点类型

- **Max 节点（庄家方）**：所有候选 move 递归，front = 子 fronts 并集（强制所有 worlds 选同一 move，解决 strategy fusion）
- **Min 节点（防守方）**：遍历所有候选 move 的并集，每个 move 做一次递归，传入更新后的 worlds 列表（剔除不合法 worlds）

#### success_rate 计算（按论文）

```
success_rate = sum(effective_value) / n
```
其中 n = 所有可能 worlds 数量，effective_value 按 three-state 处理：useful=1/0、impossible=视为1、useless=视为0。

#### 自适应参数

统一入口 `_alpha_mu_play` 按剩余牌数自适应：
- ≤4张：深度4，8s，5000 DDS预算
- ≤8张：深度4，12s，8000预算
- ≤10张：深度2，20s，15000预算
- >10张：深度1，30s，20000预算

**M参数自适应**：cards > 8时强制 M=1（PIMC），cards ≤ 8时使用配置的 `ALPHA_MU_M`（默认2）。

#### 关键优化

- **TT（转置表）**：key 不含 M_remaining，value 存 (front, best_move, M_used)，查询时使用 M_used >= M_remaining 的结果
- **根节点 Bound Reuse**：M=k 迭代时，把 M=k-1 所有候选 front 的并集作为初始 root_alpha
- **Root Cut**：未评估的候选从 M=k-1 继承结果，确保用户看到完整13张牌对比
- **时间限制**：`_time_up()` 防止搜索无限运行

### 约束系统

约束系统用于打牌阶段的手牌采样验证，核心在 `bridge/mcts/constraints.py` 和 `bridge/mcts/bid_constraint_library.py`。

#### BidConstraint 数据结构

```python
BidConstraint:
    min_hcp, max_hcp          # HCP范围
    suit_min, suit_max         # 各花色长度范围
    exact_suit                 # 精确花色长度
    min_controls               # 最少控制数
    min_hcp_target             # 目标HCP（高斯采样中心）
    specific_cards             # 特定牌张
    max_hcp_from_negative_inference  # 负推断HCP上限
    cannot_have_suit           # 不能持有的花色
    inference_source           # 推断来源（含system后缀）
```

#### 约束分类

| 类型 | 说明 | 违反后果 |
|------|------|---------|
| 硬约束 | 约定叫/叫品含义 | 采样权重=0 |
| 软约束 | 负推断（pass→≤7HCP）、点力守恒 | 软加权惩罚 |

**inference_source 优先级**：convention > negative_inference > hcp_conservation > hard_coded

#### 约束分级验证

`validate_level1/2/0()` 实现分级验证：
- **L1（硬约束）**：约定叫/叫品含义，50次重试
- **L2（放宽）**：50次重试
- **L0（仅voids）**：20次重试

### 手牌采样器

`bridge/mcts/sampler.py` 的 `DealSampler` 实现 uniform sampling with level-based constraint validation，辅以 Metropolis-Hastings（MH）引导式修复提速收敛。

**采样流程**（`_sample_one`）：
1. `_extract_known_info()`：提取已知手牌、未知牌池、剩余计数、已知缺门（void）
2. `_reduce_constraint_for_played()`：中局按已出牌扣减约束（例外：已知手牌位置不验证）
3. `_check_feasible()`：可行性预检，识别"花色约束迫使 HCP 超标"等不可行场景，直接跳过 MH/L1 空转
4. `_sample_uniform()`：逐张分配（Tier 1 优先「仍缺张+不 void 该花色+剩余需求最大」）+ 残留牌退回补齐（Tier 2），**保证世界永远完整**（绝不丢牌），违反 void 的世界由上层验证链剔除
5. 分级验证回退链：L1（MH 修复，`_sample_mh_repair`）→ L2（放宽）→ L0（仅voids）→ 兜底（`_pick_least_violating`，选违反约束最少的候选）

**MH 引导式提案**（`_propose_swap`）：按违约类型定向交换，补花色时移出最高 HCP 非目标牌避免 HCP 升高被接受率拒绝；`exact_suit` 缺长纳入花色缺长引导；补花色优先从"超过 `suit_min`"的花色移出牌，避免破坏其他花色约束；HCP 接近下限时保 HCP（移出最低非目标牌、补入最高目标牌）。多约束叠加场景（逆叫、技术性加倍）整体 MH 成功率 100%/88%。

**中局约束扣减法**：按已出牌扣减 HCP/min_controls/suit_min/exact_suit/suit_max，物理意义：初始约束 = 已出部分 + 剩余部分。

> **注**：信念状态跟踪（粒子滤波，BeliefTracker）已废弃。当前采用 uniform sampling with level-based constraint validation。`bridge/mcts/belief.py` 仅保留 `collect_voids()`（void检测）和 `collect_signal_evidence()`（LLM prompt注入用）工具函数。

### DD引擎选牌

`bridge/mcts/dd_search.py` 的 `DDSearch` 实现纯蒙特卡洛 + DirectDDS 双明手评估。

#### 选牌三层分层比较（`_compare_candidates`）

1. **第一层**：avg差 > 显著性阈值 → 按方向（庄家取高/防守取低）
2. **第二层**：rank不同 → 小牌优先（保留大牌结构）
3. **第三层**：rank相同 → 回退原始avg方向

**显著性阈值**：`threshold = Z × std_diff / √N`（配对差值检验，Z=1.0，std_diff为同world配对差值样本标准差）

#### DirectDDS

`bridge/mcts/direct_dds.py` 使用 ctypes 直接封装 DDS C库：
- `solve_all_boards_raw()`（Card-based）
- `solve_all_boards_bits()`（bitmap-based）
- 批量处理（分批≤200），比 endplay 路径快约6倍

### LLM校验层

`bridge/mcts/llm_validator.py` 规则化校验 LLM 推荐出牌：

1. **规则1**：推荐牌必须在 `playable` 中（基本合法性）
2. **规则2**：第四家"能赢却出小牌输墩"检测
3. **规则3**：第二家"小牌盖大牌"错误检测

校验失败时回退到 `_select_best_card`。

### 打牌交互流程

打牌前端状态机在 `web/src/App.jsx`，核心状态变量：

| 变量 | 含义 |
|------|------|
| `playState` | 后端返回的完整打牌状态 |
| `playInitiated` | 打牌已启动 |
| `playStarted` | 第一张牌已打出 |
| `isPlayPaused` | 暂停中 |
| `positionRoles` | 前端角色配置 `{位置: 'ai'|'human'}` |

**每墩生命周期**：
```
墩首 (cards.length === 0)
├─ 显示"继续"按钮，隐藏选牌面板
├─ 角色Toggle可切换
└─ 点击"继续": 人类领出→选牌面板，AI领出→自动出牌

墩中 (1 ≤ cards.length ≤ 3)
├─ 人类回合 → 自动暂停 + 选牌面板
├─ AI回合 → 自动出牌（可手动暂停）
└─ 点击"暂停" → 显示"继续" + "撤销"

墩完成 (cards.length === 4)
├─ 自动暂停，保存lastCompletedTrick
└─ 第13墩完成 → phase='complete' → 自动保存记录
```

**角色切换逻辑**：庄家/明手双向同步（桥牌规则：庄家替明手出牌）。

### 打牌提示词系统

`llm/prompts.py` 的打牌提示词：
- `PLAY_DECLARER_PROMPT`：庄家提示词（全局规划 + 逐墩规划）
- `PLAY_DEFENDER_PROMPT`：防守方提示词（按位置规划）
- `PLAY_COMMON_RULES` / `PLAY_COMMON_SITUATION`：通用规则

**αμ+LLM引擎提示词**包含：
- 可选出牌组（每组牌、花色、DDS等价说明、成功率）
- 对方关键大牌（未出现的关键大牌列表）
- 战略分析（数输墩、评估每组对应战术能否消除输墩）
- 叫牌过程（推断对方花色长度和大牌位置）
- 将牌清完状态、当前出牌位置
- 精确将牌统计（程序计算，LLM仅读取）

**输出字段**：推理过程、立场分析、推荐出牌、核心逻辑、备选方案、备选逻辑差异、风险提示、后续路线建议

## 前端架构

### positionRoles 统一角色管理

全部模式统一为一个维度：**positionRoles** — 每个位置是 AI 还是人类。

```javascript
{ '南': 'ai'|'human', '北': 'ai'|'human', '东': 'ai'|'human', '西': 'ai'|'human' }
```

一个位置是"练习"还是"模拟"，仅取决于该位置**有没有手牌**：
- 有手牌 → 练习模式（看到手牌，自己做决策）
- 无手牌 → 模拟实战（看到"未知"，手动输入实战叫品/出牌）

**四人叫牌合法状态**：

| 状态 | Human | AI | 说明 |
|------|-------|----|------|
| 全 AI 旁观 | 0 | 4 | 发牌默认 |
| 单人练习 | 1 | 3 | 人类参与 |
| 模拟实战 | 3 | 1 | 3人类手动输入 + 1AI建议 |
| 全手动 | 4 | 0 | 所有位置手动 |

2H+2AI 被自动修正（不允许 2-2 分）。

### 复盘模式

- **按牌复盘**（v1.43）：52张逐张回退，`reviewCursor = N` 表示前 N 张牌已出
- `playedCardCache` 尊重游标：只包含游标之前的牌灰显
- DD Hint 预录到 trick 数据：出牌时自动计算并存入

### 手牌布局

4层容器结构（v1.44）：
1. 位置定位（`fit-content`）
2. 状态管理（`renderHandWithStatus`）
3. 组件边界（`HandDisplay`根Box）
4. 手牌排列（`renderCards`）

东西家旋转溢出修复：`top: offset - (cardHeight - cardWidth)/2` 补偿旋转偏移。

## 知识库模块

### JF文档分段

`JFLoader`（[knowledge/loader.py](knowledge/loader.py)）加载docx，按连续两个空行分段，提取前3行+章节号行作为关键字。

### 树结构转换

`parse_content_to_tree()` 将约定片段转换为树结构：
- 基于 `│----` 缩进级别
- 支持双叫品关键词（如 `1D-1H`、`1C-1D`、`2D-2NT`）
- 支持第三四家开叫1高花
- 多叫品拆解：识别包含"/"的叫品行，自动拆解
- 单个字母叫品（C、D、H、S）自动推断为3阶叫品

### 树结构导航

`navigate_tree_by_bids()` 根据叫牌序列在树结构中导航：
- 自动处理根节点（跳过开叫品）
- 支持双叫品关键词和第三四家开叫的导航

## 配置说明

### 环境变量 (.env)

```env
DEEPSEEK_API_KEY=your_deepseek_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DOUBAO_API_KEY=your_doubao_api_key
DOUBAO_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
DOUBAO_VISION_ENDPOINT=your_vision_endpoint_id
DOUBAO_SEED_2_1_PRO_CHAT_ENDPOINT=your_seed_pro_chat_endpoint
DOUBAO_SEED_2_1_PRO_REASONING_ENDPOINT=your_seed_pro_reasoning_endpoint
DOUBAO_SEED_2_1_TURBO_CHAT_ENDPOINT=your_seed_turbo_chat_endpoint
DOUBAO_SEED_2_1_TURBO_REASONING_ENDPOINT=your_seed_turbo_reasoning_endpoint
```

### 关键配置 (config.py)

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `DEFAULT_DEAL_SYSTEM` | `2D/2H/2S：自然阻击` | 阻击叫体系，影响关键字提取 |
| `DEFAULT_PLAY_ENGINE` | `llm` | 默认打牌引擎 |
| `DEFAULT_MAIN_PROMPT_MODEL` | `deepseek-v4-flash` | 主提示词模型 |
| `DEFAULT_FALLBACK_MODEL` | `deepseek-v4-flash` | 备用提示词模型 |
| `MAIN_PROMPT_TEMPERATURE` | 0.2 | 主提示词温度 |
| `FALLBACK_PROMPT_TEMPERATURE` | 0.5 | 备用提示词温度 |
| `MAIN_PROMPT_MAX_RETRIES` | 2 | 主提示词合规性重试次数 |
| `FALLBACK_PROMPT_MAX_RETRIES` | 1 | 备用提示词重试次数 |
| `MCTS_ITERATIONS` | 5000 | MCTS最大迭代数 |
| `MCTS_TIME_LIMIT` | 10.0 | MCTS时间限制（秒） |
| `DD_NUM_SAMPLES` | 200 | DD采样数 |
| `DD_TIME_LIMIT` | 30.0 | DD时间限制（秒） |
| `ALPHA_MU_ENABLE` | True | 启用αμ引擎 |
| `ALPHA_MU_ENDGAME_CARDS` | 8 | αμ触发牌数阈值 |
| `ALPHA_MU_NUM_WORLDS` | 20 | αμ possible worlds数 |
| `ALPHA_MU_M` | 2 | αμ Max递归层数 |
| `ALPHA_MU_TIME_LIMIT` | 60.0 | αμ时间限制（秒） |
| `DD_PARTICLES_MIN` | 100 | DD 采样数下限 |
| `DD_PARTICLES_MAX` | 2000 | DD 采样数上限 |
| `MCTS_PARTICLES_MIN` | 300 | MCTS 迭代数下限 |
| `MCTS_PARTICLES_MAX` | 1000 | MCTS 迭代数上限 |
| `ALPHA_MU_WORLDS_MIN` | 30 | αμ world 数下限 |
| `ALPHA_MU_WORLDS_MAX` | 500 | αμ world 数上限 |
| `SIGNAL_MIN_RANK` | 8 | 防守高牌信号最低 rank |

### 端口约定

- 后端：8003（`api/main.py`）
- 前端：5173（Vite，`strictPort: true`）

### 启动方式

**启动系统**（同时启动前后端）：
1. 清理残留进程（node: vite, python: uvicorn）
2. 启动后端：`uvicorn api.main:app --host 0.0.0.0 --port 8003`（不使用 `--reload`）
3. 启动前端：`cd web && npm run dev`

## 版本历史

### v1.58
- **MH 多约束收敛（补花色保护边缘花色）**
  - `_propose_swap` 分支3 补花色时，移出的牌优先来自"超过其 `suit_min`"的花色（`protected`），避免补目标花色时把边缘花色压到约束之下（如补♦破坏♥≥5）形成振荡。验证：逆叫16+ 50% → 100%，技术性加倍 76% → 88%
  - 通过 8 种真实约束模式的整体成功率基准确认默认 `beta=1.0` 最优
- 修改文件: bridge/mcts/sampler.py, bench_mh.py

### v1.57
- **MH 死锁修复（补花色时保 HCP）**
  - `_propose_swap` 分支 3 自适应保 HCP：当"移出最高非目标牌 + 补入最低目标牌"会跌破 `min_hcp`（`vhcp - max_non_wanted < vcon.min_hcp`）时，切换为保 HCP 路径——移出最低 HCP 非目标牌、补入最高 HCP 目标牌（不超出 `max_hcp`），避免补花色破坏 HCP 下限被 Metropolis 拒绝而死锁。验证：死锁场景 MH 成功率 19% → 100%
- 修改文件: bridge/mcts/sampler.py, test_mh_fix.py

### v1.56
- **中局采样慢优化（世界完整性 + MH 收敛 + 可行性预检）**
  - `_sample_uniform` 重写：逐张分配（Tier 1 优先「仍缺张+不 void 该花色+剩余需求最大」）+ 残留牌退回补齐（Tier 2），保证世界永远完整，杜绝 void 回填失败导致的缺牌/重复世界被 DDS 丢弃
  - `_propose_swap` 补花色改移出最高 HCP 非目标牌，避免 HCP 升高被 Metropolis 接受率拒绝；`exact_suit` 缺长纳入花色缺长引导
  - `_check_feasible` 可行性预检增强：`_position_hcp_feasible` 合并 `suit_min`/`exact_suit` 并排除 exact_suit 剩余牌，识别"花色约束迫使 HCP 超标"的不可行场景，跳过 MH 空转
  - 采样回退链早收敛：MH 几乎全失败时直接走 Level 0/兜底
- 修改文件: bridge/mcts/sampler.py, dbg_repro.py

### v1.55
- **DD-αμ-LLM 引擎 LLM 审查开关**
  - `_dd_alphamu_llm_play` 新增 `enable_llm_review` 参数：关闭（默认）时中盘走 `_dd_play`、残局走 `_alpha_mu_play`（纯引擎）；开启时走原 `_dd_llm_play`/`_alphamu_llm_play`（LLM 审查）
  - API `PlayAIRequest` 新增 `use_llm_review` 字段并透传 service
  - 前端设置面板 DD-αμ-LLM 引擎下新增「纯引擎 / LLM审查」切换，PlayContext 持久化 localStorage
- **选牌决策改为完全交予概率（取消小牌优先）**
  - DD：`_compare_candidates` 取消平局小牌优先，完全按 val 方向决胜（庄家取高、防守取低）；删除 `_paired_diff_stats`、`_Z_SCORE` 死代码
  - αμ：根节点选牌本就是 `if score > best_score` 纯概率；删除 `_rank_bonus` 死代码
- 修改文件: bridge/play_service.py, api/main.py, bridge/mcts/dd_search.py, bridge/mcts/alpha_mu.py, config.py, web/src/context/PlayContext.jsx, web/src/services/api.js, web/src/App.jsx, web/src/components/SettingsPanel.jsx

### v1.54
- **DD 提示异步计算（7/8：线程化 + 参数链路）**
  - 将 DD 提示计算移出出牌请求关键路径：`_dd_hint_executor`（ThreadPoolExecutor，max_workers=1）后台线程计算，不再阻塞 play_card / ai_play 响应
  - 出牌前 `copy.deepcopy(state_before)` 快照，后台线程从快照的 current_player 取可出牌计算提示，与复盘路径 `_compute_dd_hints_for_state_from_state` 语义一致
  - 在请求线程内同步捕获目标 trick 引用（`_resolve_dd_target`），避免后台运行时状态前进导致提示错墩
- **修复 DDS 并发安全（根因）**
  - direct_dds 的 `_dll_lock` 原先只保护 DLL 加载，未保护实际求解调用
  - 扩展 `_dll_lock` 到 `solve_all_boards_raw` / `solve_all_boards_bits` / `calc_dd_table` 的 `SolveAllBoardsBin` / `CalcDDtable`，串行化所有 DDS 求解
  - 修复 7/8 线程化后后台线程与主线程并发调用 DDS 导致内部状态损坏（`Sum 3 is not four`）、进程崩溃进而丢失定约/定约方/首攻的问题
- 修改文件: api/main.py, bridge/mcts/direct_dds.py

### v1.53
- **人类出牌乐观更新**
  - 点击后立即将牌显示到当前墩并移出手牌，后端返回后用权威状态覆盖，失败时回退（reconcilePlayState）
- **AI出牌两阶段（即时思考）**
  - AI出牌拆为两个 useEffect：轮到时立即置 aiThinking=true（中心圆圈马上旋转），250ms 后再执行 handleAIPlay
- **ai_play 直接返回 state**
  - PlayAIResponse 新增 state 字段，前端不再额外调 getPlayState，减少一次往返延迟
- **牌桌防闪隐**
  - 当前墩为空时直接用 playState.tricks 最后一墩，避免刚出的牌短暂消失
  - 已出牌模式优先用顶层完整手牌，避免复盘回放时与已出牌重复计数
- **DD/αμ LLM 审查提示词 engine_name 通用化**
  - _build_strategy_text 新增 engine_name 参数，替换硬编码"αμ"
  - 移除 DD/αμ 路径两个 _validate_and_fallback 调用
- 修改文件: api/main.py, App.jsx, CardTable.jsx, play_service.py

### v1.52
- **出牌面板隐藏已出/他手的牌**
  - 默认隐藏已出/他手的牌，仅显示当前可选牌，减少点击干扰
  - 标题栏"显示全部"checkbox 恢复显示全部13张牌（灰色失效状态）
  - checkbox 为面板级本地 state，切换位置/重开面板时保持
- **打牌完成新增"复盘"按钮**
  - 打牌完成时停留在完成状态，不再自动进入本地复盘
  - "复盘"按钮从历史记录载入最新打牌完成记录，与"从历史记录载入"走同一路径
  - 修复 MainTableArea→RightPanelSwitcher 漏传 onReviewCompletedPlay 导致按钮不显示
  - 载入打牌记录后复盘游标停在全部已出位置，最后一张牌显示在牌桌上
- **载入打牌记录一步直达打牌界面**
  - loadRecordToTable 的 setShowPlayPanel 按 hasPlayState 判断
  - 自动进入打牌界面的 useEffect 不再依赖 !showPlayPanel
  - 仅叫牌完成未打牌的记录仍进入叫牌界面
- 修改文件: App.jsx, CardTable.jsx, MainTableArea.jsx, PlayDetailPanel.jsx

### v1.51
- **局况功能**
  - GameContext 新增 vulnerability/setVulnerability 状态
  - 视觉识别（VISION_PROMPT）新增局况识别
  - 后端 _normalize_vulnerability 标准化函数
  - 截屏/图片识别自动设置局况
  - 右上角局况下拉选择器（始终可见）
- **右上角/右下角信息面板布局统一**
  - 宽度统一 100px，所有标签高度 20px，字号 0.6-0.65rem
  - 右下得分合并为单标签
- **历史记录回放 phase 修复**
  - allReplayed 检测，全部回放时保留原始 phase（'complete'）
- 修改文件: GameContext.jsx, CardTable.jsx, CardTablePanel.jsx, ControlButtons.jsx, useDealing.js, doubao_client.py, api/main.py, App.jsx, SettingsPanel.jsx

### v1.50
- **DD引擎全面重构**
  - 移除 endplay 依赖，改用 DirectDDS（ctypes直接封装DDS C库）
  - `solve_all_boards_raw()` 和 `solve_all_boards_bits()` 批量求解，比 endplay 路径快约6倍
  - 信念状态跟踪（BeliefTracker）废弃，改为 uniform sampling with level-based constraint validation
  - `bridge/mcts/belief.py` 仅保留工具函数（`collect_voids`、`collect_signal_evidence`）
  - `DealSampler._sample_uniform()` 洗牌未知牌池，L1/L2/L0 分级约束验证回退链
- 修改文件: `bridge/mcts/direct_dds.py`(新增), `bridge/mcts/dd_search.py`, `bridge/mcts/sampler.py`, `bridge/mcts/belief.py`, `bridge/mcts/constraints.py`

### v1.49
- **αμ+LLM引擎开发**
  - `best_vector` 三层分组（花色 + rank区间：[2-7]low / [8-10]mid / [J-A]high）
  - LLM 策略审查：组数≥2 且组间成功率极差<15% 时触发
  - Plan 生命周期管理：步骤跟踪 + 4条件失效检测
  - Prompt 系统重构：飞牌优先识别、NT赢墩分支、5维评估、一致性约束、绝望模式
  - UI联动：模型选择 + 徽章显示（`αμ+V4-Pro·思考` 等）
  - **DeepSeek thinking参数化为可配置**：`chat()`/`chat_json()` 新增 `thinking: bool = False` 参数，默认禁用保持叫牌速度，αμ+LLM引擎"思考模式"按需启用 `thinking=True`（v1.38的"显式禁用"演进为"默认禁用+按需启用"）
  - αμ引擎统一为单一入口 `_alpha_mu_play`，按剩余牌数自适应参数
  - αμ引擎 Min 节点优化：遍历 move 并集（3-5个）替代 per-world 独立评估，复杂度从 worlds×moves 降为 moves
  - αμ引擎 TT key 不含 M_remaining，支持跨 M 命中
  - αμ引擎根节点 Bound Reuse + Root Cut
- 修改文件: `bridge/mcts/alpha_mu.py`, `bridge/play_service.py`, `llm/prompts.py`, `web/src/components/PlayDetailPanel.jsx`

### v1.48
- **αμ引擎关键修复：Min节点墩数未更新 + rank_bonus方向反转 + 前端显示墩数**
  - `_dds_evaluate_single_world` 墩数未更新bug：Min玩家打出第4张牌完成一墩后，`decl_tricks`/`def_tricks` 未更新，`remaining_tricks` 多算1墩 → αμ系统性偏好输墩。修复：当 `len(new_trick_cards) == 4` 时调用 `trick_winner()` 更新墩数
  - `_rank_bonus` 方向反转：原大牌得更高bonus，反转后小牌得更高bonus，与DD引擎"平局时小牌优先"一致
  - 前端barchart显示墩数：`72% · 10.2墩 · 18/25 · front3`
- 修改文件: `bridge/mcts/alpha_mu.py`, `web/src/components/PlayDetailPanel.jsx`

### v1.47
- **DD引擎三连修复：deal.first明手领出bug + 选牌分层比较 + 手工出牌面板**
  - `deal.first` 明手领出 bug：新增 `actual_turn` 参数传递到6个函数，5处 `deal.first` 和6处 `curplayer_pos` 改用 `actual_turn`
  - DDMC选牌分层比较：`_compare_candidates` 三层决胜（avg显著差异→小牌优先→rank相同回退avg方向），动态显著性阈值 `Z×√2×σ/√N`
  - 手工出牌GUI面板：4×13网格出牌面板替代键盘输入
- 修改文件: `bridge/mcts/dd_search.py`, `web/src/components/CardTable.jsx`, `web/src/components/HandDisplay.jsx`

### v1.46
- **复盘模式 DD Hint 与按牌回退完整重构**
  - 游标语义统一：`reviewCursor = N` 表示前 N 张牌已出
  - `playedCardCache` 尊重游标
  - `reviewTrick` / `displayTrick` 边界修复
  - 载入记录自动进入打牌
  - DD Hint 链路修复
- 修改文件: `web/src/components/CardTable.jsx`, `web/src/components/CardTablePanel.jsx`, `web/src/components/PlayDetailPanel.jsx`, `web/src/App.jsx`, `api/main.py`

### v1.45
- **DD引擎性能优化全套修复**
  - 中局约束扣减法替代比例缩减
  - 软硬约束区分（负推断/点力守恒视为软约束）
  - `solve_all_boards` 批量求解（分批≤200），600粒子性能提升5-30倍
  - 移除自写 ThreadPoolExecutor 并行（endplay dds C库非线程安全）
- 修改文件: `bridge/mcts/sampler.py`, `bridge/mcts/dd_search.py`, `config.py`

### v1.44
- **手牌布局4层容器结构重构**
  - 东西家手牌旋转溢出修复：`top: offset - (cardHeight - cardWidth)/2` 补偿
  - 手牌输入框和"未知"控件独立渲染
  - 4层容器结构：位置定位→状态管理→组件边界→手牌排列
- 修改文件: `web/src/components/CardTable.jsx`, `web/src/components/HandDisplay.jsx`

### v1.41-v1.43
- **打牌引擎大师级优化**（v1.41）
  - αμ搜索引擎（`bridge/mcts/alpha_mu.py` 新增）
  - 信念状态跟踪 + 粒子滤波（`bridge/mcts/belief.py`，v1.50已废弃）
  - 防守信号模型（`bridge/mcts/signals.py`）
  - LLM输出校验层（`bridge/mcts/llm_validator.py`）
  - 三信号关键决策检测
  - 首攻 DD + LLM 融合
  - MCTS根节点选牌修复 + rollout策略强化
- **DD Hint预录到trick数据**（v1.43）：出牌时自动计算并存入，复盘时DD hint标记
- **打牌提示词全面重写**（v1.33）：8个模板变量，防守信号体系，庄家7步分析框架

### v1.38-v1.40
- **DeepSeek V4 thinking模式显式禁用**（v1.38）：`extra_body={"thinking": {"type": "disabled"}}`，叫牌提速3-5倍
- **逼局进程强制规则**（v1.38）：禁止选择不逼叫的示弱叫品
- **暗色模式全面适配**（v1.35）
- **Tiered分层引擎重做**（v1.40）：DD替代MCTS中盘，新增Perfect DD全知引擎和人类DD提示

### v1.32-v1.37
- **打牌模块新增**（v1.32）：`play_types.py`、`play_engine.py`、`play_service.py`，5种引擎初版
- **将牌将吃Bug修复**（v1.34）：`Contract.from_str()` 花色代码与 `Card.suit` 不匹配
- **有将/无将坐庄策略分离**（v1.34）：有将数输墩、无将数赢墩
- **叫牌操作按钮迁移**（v1.37）：迁移至BiddingDetailPanel
- **记录类型枚举重构**（v1.37）：4种保存类型

### v1.29-v1.31
- **阻击叫牌体系参数传递**（v1.29）：`{deal_system}` 占位符
- **前端代码结构优化**（v1.31）：提取5个自定义Hooks，SettingsPanel组件

### v1.24-v1.28
- **双明手分析Bug修复**（v1.24）：`trump_order` 顺序错误（应为S,H,D,C,NT）
- **备用模型切换功能**（v1.24）
- **移除叫牌建议功能**（v1.28）
- **发牌人设定功能重构**（v1.28）：点击方位标签设定

### v1.19-v1.23
- **游戏管理系统**（v1.19）：`bridge/game_manager.py`，UUID游戏ID
- **API端点重构**（v1.19）：游戏管理API
- **网页版双明手分析显示优化**（v1.23）：`DoubleDummyTable.jsx`
- **双明手分析功能集成**（v1.22）：`endplay_integration.py`

### v1.13-v1.18
- **关键字提取优化系列**（v1.12-v1.13）：
  - 1NT开叫后对方争叫（12.3.x系列）
  - 1C/1D开叫后对方干扰
  - 1高花开叫后对方干扰
- **检验定约功能**（v1.18）：`/api/analyze-contract`
- **术语修正**（v1.18）："庄家"→"发牌人"（第一个叫牌的人）

### v1.8-v1.12
- **JF约定预处理功能**（v1.4/v1.8重写）：`preprocess_jf_content()`
- **树结构转换**（v1.9）：`parse_content_to_tree()`、`navigate_tree_by_bids()`
- **四种结构性约定片段处理**（v1.8重写）
- **1NT开叫后对方争叫关键字提取**（v1.12）

### v1.4-v1.7
- **JF约定预处理功能**（v1.4）：`{subsequent_bids}` 占位符
- **输出格式程序化生成**（v1.4）：`bridge/output_format.py`
- **移除后续建议功能**（v1.7）：简化预处理逻辑
- **结构性约定预处理为空时自动切换**（v1.7）：→ "成局与满贯"

### v1.1-v1.3
- **初始版本**（v1.0）：从Dify工作流转换
- **集成Deep Finesse**（v1.2）
- **历史记录功能**（v1.3）
- **叫品选择优先级修复**（v1.3）：高花>无将>低花

## 依赖项

### Python依赖
```
openai
python-dotenv
python-docx
pyautogui
pyscreeze
pillow
```

### 可选依赖
- `endplay`：双明手分析（`endplay_integration.py`，v1.50后DD引擎不再依赖）
- `mss`：截屏功能

### 前端依赖
- React 19 + Vite + MUI
- 详见 `web/package.json`
