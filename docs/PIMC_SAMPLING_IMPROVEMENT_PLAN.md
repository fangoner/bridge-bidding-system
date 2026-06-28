# 桥牌打牌引擎全面改进计划书

**目标**：通过规则校验、采样优化、知识注入、搜索增强和残局精确求解，全面提升 AI 打牌能力
**创建日期**：2026-06-28
**最后更新**：2026-06-29
**当前状态**：§2.1 PIMC 采样质量重构完成，§2.3 首攻规则库待实施

---

## 一、总体框架

```
打牌引擎改进
├── 第一阶段：快速见效（1-2天）✅ 已完成
│   └── 硬编码打牌规则校验 (llm_validator.py)
│
├── 第二阶段：核心增强（3-7天）⏳ 进行中
│   ├── 2.1 PIMC 采样质量 ← 当前焦点
│   ├── 2.2 MCTS Rollout 策略
│   ├── 2.3 首攻规则库
│   ├── 2.4 防守信号完善
│   └── 2.5 打牌知识库
│
└── 第三阶段：高级功能（1-2周）🔮 规划中
    ├── 3.1 αμ 搜索深度扩展
    ├── 3.2 残局牌型自动识别
    ├── 3.3 性能优化（并行/缓存）
    ├── 3.4 信念跟踪增强
    └── 3.5 防守方协同建模
```

### 1.1 引擎架构现状

| 引擎 | 首攻 | 中盘 | 残局 | 采样 | 选牌策略 |
|------|------|------|------|------|---------|
| **Tiered** | DD+三信号升级LLM | DD+三信号升级LLM | αμ→DD枚举 | 约束+信念 | 分层自适应 |
| **MCTS** | UCT树搜索 | UCT树搜索 | UCT树搜索 | 约束+信念 | UCT exploitation |
| **DD** | 蒙特卡洛+solve_board | 蒙特卡洛+solve_board | 蒙特卡洛+solve_board | 约束+信念 | Maximin(avg+min) |
| **αμ** | — | — | Pareto Front搜索 | 约束+信念 | Maximin最小成功率 |
| **Perfect DD** | 全知solve_board | 全知solve_board | 全知solve_board | 无 | 纯avg最优 |
| **LLM** | DeepSeek推理 | DeepSeek推理 | DeepSeek推理 | — | 自然语言推理 |

### 1.2 已识别的主要短板

| 短板 | 严重度 | 当前状态 |
|------|--------|---------|
| 采样质量 — 叫牌约束利用粗糙 | 高 | ⏳ 第二阶段 2.1 进行中 |
| MCTS Rollout 策略 — 纯随机 | 中 | ⏳ 待实施 |
| αμ 深度限制 — 残局受阻 | 中 | 🔮 第三阶段 |
| 防守较弱 — 信号+协同不足 | 中 | ⏳ 第二阶段 2.4 |
| 首攻依赖 LLM — 无规则库 | 中 | ⏳ 第二阶段 2.3 |
| 缺乏打牌知识库 | 低 | ⏳ 第二阶段 2.5 |
| 性能瓶颈 — 采样/DD评估慢 | 低 | 🔮 第三阶段 3.3 |
| 残局牌型识别缺失 | 低 | 🔮 第三阶段 3.2 |

---

## 二、第一阶段：打牌规则校验 ✅ 已完成

### 2.1 实现

硬编码基本打牌规则校验，防止 LLM 犯低级错误。

**文件**：`bridge/mcts/llm_validator.py`

**10 条核心规则**（按优先级排序）：

| # | 规则 | 级别 | 说明 |
|---|------|------|------|
| 1 | 合法性 | critical | 推荐牌必须在 playable 中 |
| 2 | 第四家原则 | critical | 能赢则用最小牌赢、同伴赢则出最小牌、不能赢则出安全牌 |
| 3 | 将牌原则 | critical | 将吃用最小将牌、不将吃同伴赢墩、有赢墩不将吃 |
| 4 | 关键墩必赢 | critical | 定约成败相关的墩必须赢 |
| 5 | 第二家原则 | error | 小牌跟小、大牌盖大牌、不浪费大牌 |
| 6 | 第三家原则 | error | 同伴出小要上大牌、同伴赢墩不超打、经济用牌 |
| 7 | 连接张出牌 | error | AK出K、KQ出Q、QJ出J（不浪费大牌） |
| 8 | 赢墩经济 | error | 赢墩永远用恰好能赢的最小牌 |
| 9 | 垫牌选择 | warning | 优先垫输张、保留赢墩潜力、不垫可能做大的牌 |
| 10 | 防守不帮飞 | warning | 不领出/回出庄家可能嵌张的花色 |

**集成**：`bridge/play_service.py` 的 `_validate_and_fallback()` 和 `_select_best_card()`，同时覆盖 DD 否决路径

**测试**：`tests/test_validator.py` — 6 个典型错误场景全部通过

---

## 三、第二阶段：核心增强 ⏳ 进行中

### 2.1 PIMC 采样质量优化（当前焦点）

#### 2.1.1 改进路径

```
叫牌序列
    │
    ▼
┌──────────────────────────────────────────────┐
│  结构化叫牌解析                                │
│  ParsedBid → AuctionBid → BiddingState        │
│  跟踪：发牌人、局况、实质性叫品、逼叫状态、       │
│        开叫方、约定叫激活、NS/EW HCP范围        │
└──────────────────┬───────────────────────────┘
                   │
    ┌──────────────┴──────────────┐
    ▼                              ▼
┌──────────────┐          ┌──────────────────┐
│ conventions  │          │ dynamic_inference│
│ 约定叫识别    │          │ 动态约束收紧      │
│ 触发→精确约束 │          │ 否定推断          │
│              │          │ HCP守恒           │
└──────┬───────┘          └────────┬─────────┘
       │                           │
       └───────────┬───────────────┘
                   ▼
┌──────────────────────────────────────────────┐
│  BidConstraint (constraints.py)               │
│  ┌─────────────┐  ┌──────────────────────┐   │
│  │ 硬约束 (0/1) │  │ 软约束 (连续惩罚)      │   │
│  │ specific_card│  │ min/max超限×2.0      │   │
│  │ exact_suit  │  │ 花色超限×3.0          │   │
│  │ min_controls│  │ 缺失大牌×8.0          │   │
│  │ void花色     │  │ balanced违反×5.0      │   │
│  └─────────────┘  └──────────────────────┘   │
└──────────────────┬───────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────┐
│  全局约束采样 (sampler.py)                     │
│  三步生成：形状 → HCP预算 → 牌张分配           │
│  高斯围绕 min_hcp_target / 首攻200次/中局3次   │
│  200次局部交换修正                             │
└──────────────────┬───────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────┐
│  粒子滤波信念跟踪 (belief.py)                  │
│  60粒子 × void硬约束 × 信号软调整              │
│  × 约束违反指数衰减 exp(-score*0.3)           │
└──────────────────┬───────────────────────────┘
                   │
                   ▼
         全引擎共享基础设施
      MCTS / DD / αμ / Tiered
```

#### 2.1.2 BidConstraint 数据结构

```python
@dataclass
class BidConstraint:
    position: str                                    # 位置
    min_hcp: Optional[int] = None                    # 最低HCP
    max_hcp: Optional[int] = None                    # 最高HCP
    balanced: Optional[bool] = None                  # True=均型, False=非均型
    suit_min: Dict[str, int]                         # 花色→最少张数
    suit_max: Dict[str, int]                         # 花色→最多张数
    exact_suit: Dict[str, int]                       # 花色→精确张数
    min_controls: Optional[int] = None               # 最少控制数 (A=2, K=1)
    min_hcp_target: Optional[int] = None             # HCP期望中心（高斯分布引导）
    specific_cards: Set[Tuple[str, str]]             # 必须持有的牌 {(suit,rank)}
    inference_source: str = "hard_coded"             # 来源标记（带体系后缀）
```

#### 2.1.3 硬编码叫牌约束库

**文件**：`bridge/mcts/bid_constraint_library.py`（~1700 行）

**已实现约定叫（13 类）**：

| 约定叫 | 函数 | 约束要点 |
|--------|------|---------|
| 技术性加倍 | `get_takeout_double_constraint()` | 12-21HCP，非均型，未叫高花≥4/低花≥3，敌花≤2 |
| 技术性加倍应叫 | `get_takeout_double_response_constraint()` | 弱0-8(平叫)/邀9-11(跳叫)/强12+(NT/扣叫) |
| 雅各比转移叫 | `get_jacoby_transfer_constraint()` | 2♦→♥≥5张0+HCP / 2♥→♠≥5张0+HCP |
| 转移后开叫人再叫 | `get_nt_rebid_constraint()` | 平叫接受15-17HCP/跳叫17HCP4张/直接进局 |
| 转移后应叫人再叫 | `get_transfer_responder_rebid_constraint()` | 2NT邀8-9/3NT选局10-15/4M关煞0-16 |
| 斯台曼 | `get_stayman_constraint()` | 1NT-2♣=8+HCP，至少一门4张高花 |
| 傀儡斯台曼 | `get_puppet_stayman_constraint()` | 2NT-3♣=0+HCP问高花 / 1NT-3♣=10+HCP逼局 |
| 兰迪争叫 | `get_landy_overcall_constraint()` | 2♣=♥♠≥4-4(10-16) / 2♦♥♠自然≥5(8-16) / 2NT=♣♦≥5-5(10-15) |
| 黑木/RKCB | `get_blackwood_constraint()` | 4NT=12+HCP满贯兴趣 |
| 1阶开叫 | `get_opening_bid_constraint()` | 1♣♦≥3张12-21 / 1♥♠≥5张12-21 / 1NT=15-17均型高花≤4 |
| 争叫 | `get_overcall_constraint()` | 1阶≥5张8-16 / 2阶≥5张11-17 / NT=均型有止 |
| 应叫 | `get_response_constraint()` | 一盖一≥4张6+ / 二盖一≥5张12+ / 加叫≥3张6-9 |
| 再叫 | `get_rebid_constraint()` | 逆叫16+非均/平叫原花12-15/跳叫原花16-18/加叫12-15/跳加16-18/NT平12-15跳18-19 |

**否定推断（从Pass推导上限）**：
- 首家Pass ≤ 11HCP
- 同伴花色开叫后Pass ≤ 5（JF≤4）
- 同伴1NT后Pass ≤ 7
- 对方开叫后Pass ≤ 7

**HCP守恒**：总HCP=40，`pers_max = side_total_max - partner_min_hcp`，带 `min>max` 反序自动修正

**双系统切换**：有叫牌历史→JF约定（`SYSTEM_JF`），无→标准自然（`SYSTEM_NATURAL`），`inference_source` 含体系后缀

**约定叫优先级**：`_merge_constraints` 来源优先级 — convention > negative_inference > hcp_conservation > hard_coded

**关键实现细节**：
- 约定叫检测在 `is_rebid` 分支之前执行
- bid history 解析保留 pass 维持正确顺序（避免将应叫误分类为争叫）
- 转移叫接受属于开叫人再叫

#### 2.1.4 约束分类体系

| 类别 | 来源 | 违反处理 | 示例 |
|------|------|---------|------|
| **硬约束** | 约定叫确定性要求 | 权重归零 | void有牌、specific_cards缺失 |
| **软约束** | 否定推断/HCP守恒/信号 | 指数衰减 | Pass后超上限、花色偏差 |
| **动态约束** | 后续叫品收紧 | 逐步收窄 | 开叫12-21→再叫缩小到12-15或16-18 |

#### 2.1.5 全局约束采样算法

三步生成（经验：随机+重试在严格约束下效率极低，直接构造+局部交换更可靠）：

1. **形状分配** `_generate_valid_shape_distribution()` — 满足每家每花色 min/max/exact
2. **HCP预算** `_allocate_hcp_budget()` — 高斯围绕 `min_hcp_target`，避免高牌偏倚
3. **牌张分配** `_assign_cards_by_shape_and_hcp()` — 大牌优先给需要HCP的位置 + 1000次交换修正

- 首攻前：200次硬约束重试
- 中局：3次软约束（剩余牌无法满足整手约束），违反通过 `exp(-score*0.3)` 惩罚

#### 2.1.6 粒子滤波信念跟踪

**文件**：`bridge/mcts/belief.py`

- 60 粒子，`_particle_weight()` = void(0/1) × 信号(×1.3/×0.7) × 约束(exp(-score×0.3))
- 视角感知缓存键：`(已出牌数, 当前玩家, 搜索视角)` — 同墩复用提升 ~75%
- 极端退化回退：全粒子被void过滤→均匀权重

#### 2.1.7 缺失约定叫（待补充）

**P0（高频，立即补充）：**
负加倍、支持性加倍、第四花色逼叫、斯台曼后续、朱瑞Drury

**P1（中频，一周内）：**
XYZ约定叫、新低花逼叫、弱二套质量增强、迈克尔扣叫、反常无将、爆裂叫、德克萨斯转移、斯莫伦

**P2（低频，按需）：**
莱本索尔、控制扣叫、大满贯逼叫5NT、乔丹2NT、好坏2NT、伯根加叫、反冲问叫

#### 2.1.8 架构升级：结构化叫牌解析

当前 `_normalize_bid()` 返回简单 `(level, suit)` 元组。需升级为结构化对象：

```python
@dataclass
class ParsedBid:
    level: int; suit: str; is_pass: bool; is_double: bool; is_redouble: bool
    is_jump: bool; is_reverse: bool; is_new_suit: bool; is_raise: bool; is_nt: bool

@dataclass
class AuctionBid(ParsedBid):
    position: str; bid_index: int; substantive_index: int; passed_before: bool

@dataclass
class BiddingState:
    dealer: str; vulnerability: str
    auction: List[AuctionBid]; substantive_bids: List[AuctionBid]
    constraints: Dict[str, BidConstraint]
    forcing: bool; game_forcing: bool
    opening_side: str; last_substantive_bidder: str
    current_bid_level: int; current_bid_suit: str
    convention_active: Optional[str]
    ns_hcp_range: Tuple[int, int]; ew_hcp_range: Tuple[int, int]
```

**模块拆分**：`bid_constraint_library.py`(~1700行) → `conventions.py` + `dynamic_inference.py` + `bidding_state.py`

**动态约束收紧**：后续叫品以交集方式收窄前面约束（min取大、max取小，不替换）

#### 2.1.9 2.1 子任务状态

| 子任务 | 状态 |
|--------|------|
| BidConstraint扩展 + 硬编码库 | ✅ 完成 |
| 全局约束采样三阶段生成 | ✅ 完成 |
| 粒子滤波信念跟踪 | ✅ 完成 |
| 全引擎集成 (MCTS/DD/αμ/Tiered) | ✅ 完成 |
| 10项关键Bug修复 | ✅ 完成 |
| 缺失约定叫补充 (P0/P1/P2) | ⏳ 待实施 |
| 结构化 ParsedBid/BiddingState | ⏳ 待实施 |
| 模块拆分 (conventions/dynamic_inference/bidding_state) | ⏳ 待实施 |
| 动态约束收紧 | ⏳ 待实施 |
| 批量基准测试 + 四组消融实验 | ⏳ 待实施 |

---

### 2.2 MCTS Rollout 策略改进

**当前状态**：Rollout 采用 `RandomizedRollout`（80%启发式+20%随机），启发式策略较简单

**改进方向**：

1. **领出策略增强**
   - 首攻后跟牌阶段，领出优先：长套（≥4张）→ 连接张顶张 → 短套中间张
   - 根据叫牌信息选择攻击性/保护性领出

2. **跟牌策略细化**
   - 第二家：小牌跟小（保留大牌）、大牌盖大牌（有升级潜力时）
   - 第三家：同伴领出小→上大牌、同伴赢墩→跟最小
   - 第四家：能赢用最小赢、同伴赢出最小、不能赢出安全张

3. **将牌使用规则**
   - 将吃用最小将牌、不将吃同伴赢墩、将牌长度≥3时优先清将

4. **垫牌策略**
   - 优先垫最短套小牌（保留长套赢墩潜力）
   - 不垫可能做大的中间张

**实现**：增强 `bridge/mcts/rollout.py` 的 `HeuristicRollout` 和 `RandomizedRollout`

---

### 2.3 首攻规则库

**当前状态**：首攻严重依赖 LLM，无系统化的规则库

**改进方向**：

1. **标准首攻约定**
   - 长四首攻（≥4张套第四大）
   - 连接张顶张首攻（KQJ→K, QJT→Q）
   - A 首攻（有 K 支持或有将吃需求时）
   - 短套首攻（有将牌控制时的将吃路线）

2. **叫牌引导首攻**
   - 对方叫过某花色→避免该花色首攻
   - 同伴叫过某花色→优先攻同伴花色
   - 敌方未叫花色→考虑进攻性首攻
   - 敌方成局定约→保护性首攻 > 攻击性首攻

3. **防守信号首攻**
   - 态度首攻：攻长套第四大=欢迎回攻
   - 连接张首攻：攻顶张=有连接张实力

**实现**：`bridge/mcts/lead_strategy.py`

---

### 2.4 防守信号完善

**当前状态**：`signals.py` 已实现态度/张数/花色偏好三类信号的基础提取

**改进方向**：

1. **张数信号细粒度推理**
   - 从"偶数/奇数"推断具体张数范围，更新粒子花色长度分布

2. **花色偏好信号上下文解读**
   - 结合叫牌和已出牌，LLM 解读同伴垫牌意图 → 更新信念权重

3. **信号可靠性权重**
   - 先验：同伴信号 80% 可靠
   - 根据对手水平和局势动态调整

4. **反信号推理**
   - 对手可能发假信号，引入 Bayesian 更新而非二值判定

---

### 2.5 打牌知识库

**当前状态**：LLM 提示词包含通用打牌规则，但缺乏系统化的牌型打法知识

**改进方向**：

1. **常见牌型打法模板**
   - 飞牌：简单飞/双飞/将吃飞牌
   - 投入：剥光→投入→逼出赢墩
   - 挤牌：简单挤/双挤/三挤
   - 消去打/坚壁清野

2. **特定局势打法**
   - 将牌 4-4 配合 → 边花将吃路线
   - 无将定约 → 长套树立路线
   - 防守方 → 逼将/缩短将牌

3. **注入方式**
   - 残局牌型匹配 → 自动注入对应打法提示词
   - 不替代搜索，作为 LLM 决策的上下文增强

---

## 四、第三阶段：高级功能 🔮 规划中

### 3.1 αμ 搜索深度扩展

**当前**：`alpha_mu.py` 残局≤8张触发，max_depth=4，20 worlds

- 迭代加深替代固定深度
- 引入 transposition table 避免重复搜索
- 增量 world 生成（先10个快速筛选→再加到100个精细评估）

### 3.2 残局牌型自动识别

- 识别单套结构（坚壁清野、消去打法等）并触发精确打法
- 识别挤牌条件（威胁张+忙张+时机）
- DD 结果与实际得分差距≥2墩 → 触发深度分析

### 3.3 性能优化

- DD 采样并行化（需先验证 `solve_board` 线程安全性，不安全用 multiprocessing）
- MCTS 树跨墩复用（已完成墩的子树可复用，预计提升30-50%）
- 粒子跨墩 Bayesian 更新（减少 `_sample_once()` 调用，预计减少40-60%开销）
- 信念跟踪缓存命中率监控

### 3.4 信念跟踪增强

- 更多粒子（60→200 或自适应）
- 重采样策略改进（系统重采样 vs 多项式重采样）
- 引入 particle diversity 度量，退化时触发重采样
- 缓解 Strategy Fusion 问题

### 3.5 防守方协同建模

- 防守方之间的信号约定和同伴默契建模
- 防守计划共享（类似庄家-明手之间的 `declarer_plan`）
- 动态角色分配（主动防守方 vs 被动防守方）

---

## 五、架构债务

以下问题应在第二阶段推进过程中逐步清理：

| # | 问题 | 修复方案 | 优先级 |
|---|------|---------|--------|
| 1 | `DealSampler` 双重职责（采样+信念管理） | 信念跟踪完全移到 `BeliefTracker` | P1 |
| 2 | 全局采样回退路径静默降级 | 回退时记录 warning + 降级到均匀随机 | P1 |
| 3 | `_particle_weight` 与 `compute_sample_violation_score` 逻辑重叠 | void检查移到最前面短路 | P1 |
| 4 | `_compute_hcp` 在 `constraints.py` 和 `sampler.py` 重复定义 | 统一到 `constraints.py` | P1 |
| 5 | `bid_constraint_library.py` 1700行单体 | 拆分为 conventions/dynamic_inference/bidding_state | P2 |
| 6 | `config.py` 30+配置项缺乏分组文档 | 按功能分5组 + 标注默认值依据 | P2 |
| 7 | `_normalize_bid()` 返回简单元组 | 升级为 `ParsedBid`/`AuctionBid` 结构化对象 | P2 |

---

## 六、风险评估

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 硬编码约束与 JF 文档不一致 | 中 | 高 | JF 序列抽样对照 + 边界测试 |
| 模块拆分引入回归 bug | 中 | 中 | 拆分前补全测试，渐进迁移保留 fallback |
| BiddingState 增加复杂度 | 低 | 低 | 渐进引入，旧路径保留 |
| 粒子退化（全被 void 过滤） | 中 | 中 | 已实现均匀权重回退 |
| `solve_board` 线程不安全 | 高* | 高 | 并行前验证，不安全和用多进程 |
| 明手视角 bug 回归 | 低 | 高 | 回归测试显式覆盖 |

*仅在做并行采样时触发

---

## 七、执行路线图

### 近期（1-3 天）— 第二阶段 2.1 采样质量收尾

```
Day 1  上午  运行 benchmark 建立基线（8副→记录所有指标）
       下午  补充 P0 缺失约定（负加倍/支持性加倍/第四花色逼叫/Drury/斯台曼后续）
       晚上  约束正确性验证（20个JF序列抽样对照）

Day 2  上午  扩展 benchmark → 20副 + 四组消融实验(A/B/C/D)
       下午  收集数据：约束满足率/降低与DD差/做成率提升
       晚上  根据结果调整约束严格程度

Day 3  上午  架构债务 #1-#4 清理
       下午  ParsedBid/AuctionBid/BiddingState 数据结构实现
       晚上  综合评估报告
```

### 中期（4-7 天）— 第二阶段 2.2-2.5

```
Day 4  首攻规则库 (lead_strategy.py) + 防守信号增强
Day 5  MCTS Rollout 策略改进 + 打牌知识库模板
Day 6  模块拆分 (conventions/dynamic_inference/bidding_state)
Day 7  动态约束收紧 + 集成测试
```

### 远期（2-4 周）— 第三阶段

```
Week 1-2  αμ 深度扩展 + 残局牌型识别
Week 2-3  性能优化（并行/缓存/树复用）
Week 3-4  信念增强 + 防守协同
```

---

## 八、诊断工具

| 工具 | 用途 | 优先级 |
|------|------|--------|
| `GET /api/play/diagnostics` | 约束提取/粒子统计/缓存命中率/BiddingState快照 | P0 |
| 采样可视化日志 (JSON lines) | 墩级：粒子数/void过滤数/权重分布 | P1 |
| 约束提取回溯 | 每个叫品→匹配函数→约束的追溯链 | P1 |
| 一键复现脚本 | debug_play.py增强版（种子/定约/引擎参数） | P1 |

---

## 附录 A：关键文件索引

| 文件 | 作用 | 状态 |
|------|------|------|
| `bridge/mcts/llm_validator.py` | 10项打牌规则校验（第一阶段） | ✅ 生产 |
| `bridge/mcts/constraints.py` | BidConstraint + validate_sample + compute_sample_violation_score | ✅ 生产 |
| `bridge/mcts/bid_constraint_library.py` | 硬编码约束库（~1700行，将拆分） | ✅ 待拆分 |
| `bridge/mcts/sampler.py` | 全局约束采样三阶段生成 | ✅ 生产 |
| `bridge/mcts/belief.py` | 60粒子滤波 + void/信号/约束加权 | ✅ 生产 |
| `bridge/mcts/signals.py` | 态度/张数/花色偏好信号提取 | ✅ 生产 |
| `bridge/mcts/search.py` | MCTS搜索：Determinization+UCT | ✅ 生产 |
| `bridge/mcts/dd_search.py` | DD蒙特卡洛+Maximin选牌 | ✅ 生产 |
| `bridge/mcts/alpha_mu.py` | αμ残局Pareto Front搜索 | ✅ 生产 |
| `bridge/mcts/rollout.py` | HeuristicRollout + RandomizedRollout | ✅ 待增强 |
| `bridge/play_service.py` | 六引擎调度 + Tiered分层 + LLM校验 | ✅ 生产 |
| `config.py` | 30+打牌配置项 | ✅ 生产 |
| `bridge/mcts/bidding_state.py` | ParsedBid/AuctionBid/BiddingState | 🔧 待建 |
| `bridge/mcts/conventions.py` | 约定叫识别模块 | 🔧 待建 |
| `bridge/mcts/dynamic_inference.py` | 动态收紧+否定推断+HCP守恒 | 🔧 待建 |
| `bridge/mcts/lead_strategy.py` | 首攻策略规则库 | 🔧 待建 |
| `bridge/mcts/tree_reuse.py` | MCTS树跨墩复用 | 🔧 待建 |
| `bridge/mcts/profiler.py` | 性能探针（统一计时+统计） | 🔧 待建 |

## 附录 B：快速启动命令

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8003 --reload   # 后端
cd web && npm run dev                                        # 前端
python tests/debug_play.py                                   # 调试固定牌局
python tests/test_full_play_benchmark.py                     # 基准测试
python -m cProfile -o profile.out tests/test_full_play_benchmark.py  # 性能剖面
```

## 附录 C：前端工程约定（独立于打牌引擎）

- 领域专用逻辑封装为自定义 hooks（`useModelSettings`、`useDealing`）
- `MainTableArea` 负责响应式布局，避免桌面/手机代码重复
- 状态和 setter 从正确的 Context provider 解构
- lint 自动修复脚本可能意外删除必要 props，运行后需手动验证

---

*文档更新时间: 2026-06-29*
*整合框架：原始三阶段总体计划 + PIMC采样详细方案 + 硬约束规范 + 工程约定*

---

## 变更日志

### 2026-06-29 — §2.1 PIMC 采样质量重构

**架构决策：信念粒子层重构**

1. **粒子数 × 引擎解耦**：DD/MCTS/αμ 各自独立配置粒子数
   - DD: 200 (100-500)，全量遍历不抽取，加权平均选牌
   - MCTS: 500 (300-1000)，加权 draw 池
   - αμ: 30 (20-50)，possible worlds 全量
   - Tiered: 中盘 DD(200) + 残局 αμ(30)，各设各的

2. **DD 不抽取模式**：`dd_search.py` 重构 — 从 `draw()` 有放回循环改为 `get_all_particles()` 全量遍历
   - 消除重复 world 浪费（60 粒子 → 100 次 draw 只有 50 个唯一世界）
   - 权重开根号平滑（`w^0.5`）防止极端粒子一家独大
   - 选牌从等权平均改为加权平均

3. **rank_bonus 削弱**：`/50` → `/200`，从 0.22 墩降到 0.055 墩
   - 修复 K 牌被 rank_bonus 惩罚导致防守方误选小牌的 bug
   - 原则：平局裁决的作用范围应 ≤ 统计噪声

4. **叫牌约束可视化**：后端格式化 + 前端自动展示
   - `_format_constraints_for_display()` 将约束转为可读文本
   - 六引擎全部注入 `full_output["叫牌约束"]`

5. **约束分析三层架构**：
   - 第一层：硬编码库（正则匹配序列格式）
   - 第二层：含义文本解析（复用叫牌阶段 LLM 输出，正则提取 HCP/花色）
   - 第三层：LLM 补充（仅前两层为空时触发）
   - 修复 `bid_history` → `seqStr` 传入、`return None` 缺失 bug

6. **前端设置面板**：引擎下拉框旁按需显示粒子滑块
   - DD 引擎 → DD 粒子滑块
   - αμ 引擎 → αμ 粒子滑块
   - MCTS 引擎 → MCTS 粒子滑块
   - Tiered → 中盘 + 残局两个滑块
   - 移除冗余的"采样数"输入框
   - localStorage 持久化 + 启动时同步后端

7. **出牌记录折叠**：`PlayDetailPanel` 出牌记录区可折叠，AI 输出始终可见

8. **αμ 引擎显示修复**：引擎标签链增加 `alphamu` 分支，不再误显示 "V4-Flash"

**修复的 Bug**：
- `_get_bid_constraints()` 返回 `None`（缺正常路径 return）
- `_alphamu_full_play` 未设置粒子数
- 外层 Collapse 吞掉出牌记录折叠按钮
- SettingsPanel flexWrap 导致发牌设置换行
- `BELIEF_ALPHA_MU_PARTICLES` 导入缺失
