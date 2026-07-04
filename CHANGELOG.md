# 开发日志

## 2026-07-05

### DD引擎性能优化全套修复（约束缩减 + 软硬约束区分 + 批量求解）

**背景**: 之前P0/P1/P2优化方案引入了多个bug：DD引擎0ms不执行（NameError）、300粒子首张牌卡住（HCP预算9800次重试）、prepare阶段16秒慢（300次降级到 `_distribute_biased`）、`hcp_conservation` 硬约束矛盾导致fallback。用户多次拒绝降级方案，要求从根本逻辑上修正约束处理。

**改进**:

#### 1. 中局约束扣减法（替代比例缩减）
- **问题**: 之前用 `ratio = target/13` 比例缩减 HCP/min_controls/suit_min，物理意义错误——假设HCP均匀分布在13张牌中，但HCP实际集中在A/K/Q/J上
- **修复** (`sampler.py#L1425-L1486`): 改为按已出牌扣减
  - `min_hcp = max(0, 初始min - 已出HCP)`
  - `max_hcp = max(初始max - 已出HCP, min_hcp)`
  - `min_controls = max(0, 初始min - 已出控制数)`
  - `suit_min = max(0, 初始suit_min - 该花色已出张数)`
  - `exact_suit = max(0, 初始exact - 该花色已出张数)`
  - `suit_max = max(0, 初始suit_max - 该花色已出张数)`
- **物理意义**: 初始约束 = 已出部分 + 剩余部分 → 剩余约束 = 初始约束 - 已出部分

#### 2. 软硬约束区分（HCP预算硬可行性检查）
- **问题**: `negative_inference`（pass→≤7HCP）和 `hcp_conservation`（点力守恒推断）的 max_hcp 被当作硬约束参与 `_allocate_hcp_budget` 可行性检查，导致 `sum_max < pool_hcp` 误判为不可行，所有粒子降级到 `_distribute_biased`（每次50ms × 300 = 15秒）
- **修复** (`sampler.py#L1069-L1091`):
  ```python
  _SOFT_SOURCES = {"negative_inference", "hcp_conservation"}
  is_soft = bool(c and c.inference_source in _SOFT_SOURCES)
  mn = c.min_hcp if c and c.min_hcp is not None and not is_soft else 0
  if c and c.max_hcp is not None and not is_soft:
      mx = c.max_hcp
  else:
      mx = 37
  ```
- **原理**: 软推断信息由 `compute_sample_violation_score` 软加权处理（违反约束→粒子权重降低，但不丢弃），只有明确叫牌承诺（hard_coded/meaning_parsed/convention）才参与硬可行性检查

#### 3. solve_all_boards 批量求解（替代串行 solve_board）
- **问题**: 串行 `solve_board` 600粒子耗时 1.3-10秒，p99 80ms，max 106ms；自写 ThreadPoolExecutor 并行会导致 Windows 堆损坏崩溃（0xC0000409）
- **诊断过程**:
  1. 先尝试 `ThreadPoolExecutor` 并行 → 进程崩溃（endplay dds C库非线程安全）
  2. 改用 endplay 官方 `solve_all_boards` 批量API → IndexError
  3. 加诊断日志打印失败Deal的PBN → 发现单个 `solve_board` 都OK
  4. 二分查找数量临界点 → **C库硬限制 `MAXNOOFBOARDS=200`**
- **修复** (`dd_search.py#L259-L387`):
  - 新增 `_build_deal_for_world` 提取Deal构建逻辑
  - 新增 `_solve_batch` 分批调用 `solve_all_boards`，每批 ≤ 200
  - 失败时打印PBN诊断信息，该批降级到串行
- **效果**（600粒子）:
  - 串行: avg 2-17ms, max 41-106ms, total 1.3-10s
  - 批量: avg 0.3-4.3ms, max 0.4-4.9ms, total 0.2-2.6s
  - **提升 5-30倍**

#### 4. 其他调整
- `DD_TIME_LIMIT`: 15s → 30s（允许首攻冷启动完整跑完）
- `BELIEF_DD_PARTICLES_MAX`: 1500 → 2000（批量模式下30s预算可承载）
- 移除自写 ThreadPoolExecutor 并行代码（Windows崩溃根因）
- 新增 `[DD_STATS] mode=BATCH/SERIAL` 日志区分批量/串行模式
- 新增 `[BATCH]` / `[BATCH_FAIL]` 批量求解诊断日志

**修改文件**: `bridge/mcts/sampler.py`, `bridge/mcts/dd_search.py`, `config.py`

**测试验证**:
- 600粒子全批量模式（batches_ok=3, fallback=0）
- prepare时间从16s降到0.5-1.4s
- 总出牌时间从14.9s降到0.5-2.8s（提升5-30倍）
- HCP_BUDGET_FAIL 从14条降到0条（软硬约束区分有效）
- 无 BATCH_FAIL，无崩溃

### 历史问题修复记录（本日）

| 问题 | 根因 | 修复 |
|------|------|------|
| DD引擎0ms不执行 | P0引用 `state.tricks` 但函数无state参数 → NameError | 添加 `played_set` 参数 |
| JF约定无法加载 | DD PBN错误"Sum 3 is not four"导致请求堆积超时 | 重启后端 |
| 300粒子首张牌卡住 | HCP预算9800次重试（负推断max_hcp过严） | 软硬约束区分 |
| prepare 16秒慢 | 300次降级到 `_distribute_biased` | 软硬约束区分 |
| P1-parallel崩溃 | endplay dds C库非线程安全，Windows堆损坏 | 移除并行，用 solve_all_boards |
| solve_all_boards IndexError | C库 MAXNOOFBOARDS=200 硬限制 | 分批 ≤ 200 |
| 中局约束矛盾 | 比例缩减物理意义错误 | 改为按已出牌扣减 |

## 2026-07-03

### 手牌布局4层容器结构重构 + 输入框/"未知"控件独立渲染

**背景**: 东西家手牌旋转后溢出容器（向下偏移13.65px），且手牌输入框在renderHandWithStatus内嵌渲染导致东西家布局复杂、白天模式字体看不清。通过调试4层容器结构定位根因，并将输入框和"未知"控件独立渲染。

**改进**:
- **东西家手牌旋转溢出修复** (`HandDisplay.jsx#L244`): 手牌Box旋转90°后视觉范围向下偏移 `(cardHeight - cardWidth) / 2 = 13.65px`，通过 `top: offset - (cardHeight - cardWidth) / 2` 向上补偿，使手牌视觉范围与第4层layout box对齐
- **手牌输入框独立渲染** (`CardTable.jsx`): 新增 `renderIndependentHandInput(position)` 函数，四家用绝对定位独立渲染（西: `left:0,top:50%,translateY(-50%)`；东: `right:0`；北: `top:0,left:50%,translateX(-50%)`；南: `bottom:0`），距桌面边框30px（通过card-table-container的padding），TextField固定宽度120px，renderHandWithStatus内showInput/showPlayHandInput分支留空
- **"未知"控件独立渲染** (`CardTable.jsx`): 新增 `renderIndependentUnknown(position)` 函数，人类位置无手牌时显示"未知"，位于InfoBar顶部边缘与桌面边缘正中间（`top: calc(25% - 71px)` 等，用 `translate(-50%, -50%)` 中心定位），固定尺寸90×46px，字体1.4rem加粗，白天模式 `color: '#1a1a1a'` + 半透明白底增强可读性
- **renderHandWithStatus简化**: 删除内嵌的南北家输入框代码（约70行），showInput/showPlayHandInput和"未知"分支统一留空，由独立控件渲染
- **输入框白天模式可读性**: TextField输入文字 `color: '#1a1a1a'`，helperText `rgba(0,0,0,0.85)`，背景纯白底，边框 `rgba(0,0,0,0.23)`
- **调试边框清理**: 第1层（4家位置定位容器）和第2层（renderHandWithStatus根Box）的调试边框已清理为 `border: 'none'`

**修改文件**: `web/src/components/CardTable.jsx`, `web/src/components/HandDisplay.jsx`

**测试验证**: 刷新页面确认东西家手牌不再溢出容器，四家输入框独立渲染且距桌面边框30px，"未知"控件在InfoBar与桌边正中间且四家尺寸一致，白天模式字体清晰可读

### 4层容器结构说明（调试成果）

- **第1层**（位置定位容器，CardTable.jsx）: `position: absolute` + `fit-content`，四家紧贴桌面四边
- **第2层**（renderHandWithStatus根Box）: `position: relative` + `display: flex`，状态管理（信息栏/AI输入框/未知/手牌切换）
- **第3层**（HandDisplay根Box）: `width/height: auto`，组件边界
- **第4层**（renderCards手牌排列Box）: `position: relative` + 固定尺寸，手牌绝对定位排列

**关键认识**: `fit-content` 只计算layout尺寸，不计算 `position: absolute` 子元素或 `transform` 后的视觉溢出。东西家牌因 `top: offset - 13.65px` 视觉上向上溢出第4层layout box，但layout尺寸不变。

## 2026-07-02

### 复盘改为按牌回退 + DD Hint 预录

- **后端** (`bridge/play_types.py`): Trick 新增 `dd_hints` 字段（`List[Optional[dict]]`），与 cards 平行存储每张牌打出时的 DD 全量评估；`to_dict()` 序列化包含 dd_hints；`undo_last_card()` 撤销时同步 pop
- **后端** (`api/main.py`): 提取 `_compute_dd_hints_for_state()` 共享函数供复用；新增 `_record_dd_hint()` 在每次出牌前计算 DD 评估并录入 trick；`POST /api/play/card` 和 `POST /api/play/ai-play` 均自动录入
- **前端** (`PlayContext.jsx`): `reviewCursor` 语义从墩序号(0~12)改为牌序号(0~51)
- **前端** (`CardTablePanel.jsx`): 新增 `allPlayedCards` 全局牌序列 + 按牌序号查找 `reviewTrick` 派生逻辑
- **前端** (`PlayDetailPanel.jsx`): 出牌记录改为按牌渲染：游标前正常、游标位置黄色高亮、游标后灰化（opacity 0.3 + grayscale）；导航显示"第N/52张"；每牌旁 DD hint Chip（最优=绿色，非最优=橙色）；移除独立的"复盘"按钮
- **前端** (`CardTable.jsx`): 中心标签"第N墩·第M张"；复盘墩中游标之后的牌灰化
- **前端** (`App.jsx`): `handleRewindToTrick` 参数改为 cardIdx（内部转 trickIdx）；onReviewNext 边界改用总牌数；初始 reviewCursor 统一为最后一张牌
- **前端** (`MainTableArea.jsx`): 移除 onStartReview prop 传递链路
- 打牌完成后直接显示复盘箭头和"从此重打"按钮，无需额外点击
- DD hint 随 trick 数据存入记录/备份，导入时自动恢复

## 2026-07-01

### 记录服务器端自动备份

- **后端** (`api/main.py`): 新增 `POST/GET /api/records/backup` 端点，记录保存到 `bridge_records_backup.json`（去重，最多200条）
- **前端** (`useBridgeRecords.js`): 每次增删改操作后 debounce 2s 自动同步到服务器；`loadRecords` 时若 localStorage 为空自动从服务器恢复
- 解决浏览器 localStorage 被清除后记录全部丢失的问题

### 打牌界面"返回叫牌"按钮

- `PlayDetailPanel.jsx`: 新增"返回叫牌"按钮（标题栏右侧），点击确认后清除打牌数据，回到叫牌界面，保留手牌和叫牌序列
- `App.jsx`: 新增 `handleBackToBidding` 函数
- `MainTableArea.jsx`: 传递回调

### RKCB 对方问叫不得答叫 + 将牌判定修复

- **HUMAN_BID_PROMPT** (`llm/prompts.py`): 新增"关键规则"节 — 对方问叫不得答叫、将牌只能来自我方叫品（带示例）、5NT后续叫品规则（6阶将牌=止叫不显示将牌K）
- **BIDDING_FALLBACK_PROMPT**: 关键张计算新增前置检查（对方问叫→立即停止）；第一步将牌判定明确排除对方花色；配合花色规则禁止使用对方叫品；5NT后续规则
- 修复了两个典型错误：(1) 东家错误答叫北家的4NT问叫 (2) 将牌误判为对手的♠而非我方的♣ (3) 6♣误解为边花K而非止叫

### 手牌面板显示当前LLM模型

- `CardTable.jsx`: 手牌位置角色切换按钮处，"AI"替换为当前模型缩写+版本号
- 映射: `deepseek-v4-flash`→`DSF 4`, `deepseek-v4-pro`→`DSP 4`, `doubao-seed-2.1-pro`→`DBP 2.1`, `doubao-seed-2.1-turbo`→`DBT 2.1`
- 叫牌阶段显示 fallbackModel，打牌阶段显示 playModel

### Pass 叫品记录遗漏修复

- `App.jsx`: AI异常回退pass (catch块) 和双人模式对方自动pass 两处漏写 `aiBiddingHistory`，导致下拉框和简单显示中缺失

## 2026-06-30

### αμ 候选牌超时截断修复（两轮）

**背景**:
αμ 搜索在 13 张牌场景下，候选牌列表无序 + 超时不足导致末尾候选牌被批量截断。首轮修复了排序和自适应参数，但超时截断仍会丢弃剩余候选牌。

**第一轮修复**（已在工作区）:

#### 候选牌排序 (`bridge/mcts/alpha_mu.py`)
- 将牌按 rank 升序（小将牌先评估，用于将吃决策）
- 副牌按 rank 降序（大牌先评估）
- 确保重要候选牌优先被评估，超时时丢的是末尾小牌

#### 自适应 worlds + 超时 (`bridge/play_service.py`)
- worlds 随牌数减少线性放大：13张→base, 12→2×base, ... 4→10×base (cap 100)
- `ALPHA_MU_NUM_WORLDS` 从 30 降到 20（`config.py`）
- >12 张牌时间上限从 30s 提升到 60s

**第二轮修复**（今日完成）:

#### 超时快速 DD 回退 (`bridge/mcts/alpha_mu.py`)
- **核心改动**：当 `_time_up()` 触发截断时，对剩余候选牌执行快速 DD 叶节点评估（`_evaluate_leaf`），而非直接丢弃
- 快速评估跳过递归搜索（Max→Min→...），只做单层 DD 求解
- 速度：每张剩余牌 ~N_worlds 次 DDS（vs 完整递归的 N×depth×branching 次），快 5-10 倍
- 快速评估结果标记 `quick: True`，选牌时完整 αμ 搜索优先（同分时 `is_quick=0 > is_quick=1`）
- 推理输出标注 `⚡` 和快速评估数量（如 "1 quick-DD"）

**测试验证**:
- 简单场景（单花色）：12/12 全评估，0.9s完成
- 复杂场景（缺门+多花色）：3s 限制下 13/13 全评估（1 张 quick-DD），之前丢失 2 张
- 测试文件：`tests/debug_timeout_check.py`、`tests/debug_timeout_complex.py`

**待后续研究**:
- 极端复杂局面（DDS 30ms/次）60s 仍可能不足，但快速回退确保所有候选至少得到叶节点评估
- `_build_child_state` 浅拷贝风险（出现 "Wrong number of remaining cards" 但未稳定复现）
- 可能的方向：按 DDS 平均耗时自适应调整 timeout、残局求解器替代 DDS

## 2026-06-29

### PIMC 采样质量重构：信念粒子层架构重设计

**背景**:
原有的 60 粒子 + 有放回 draw 模式存在三大缺陷：(1) DD 100 次采样仅~50 个唯一世界，浪费一半 solve_board；(2) 粒子数与引擎需求不匹配（DD 需要多样本、αμ 需要克制）；(3) 叫牌约束可视化缺失，无法诊断采样质量。

**改进**:

#### 1. 引擎独立粒子数 (`config.py`, `play_service.py`)
- DD: 200 粒子 (100-500)，全量遍历不抽取，加权平均选牌
- MCTS: 500 粒子 (300-1000)，加权 draw 池，UCT 自带多样性
- αμ: 30 粒子 (20-50)，possible worlds 全量，N×M DDS 昂贵
- Tiered: 中盘 DD(200) + 残局 αμ(30)，各阶段独立设置
- 前端设置面板：引擎下拉框旁按需显示对应粒子滑块

#### 2. DD 不抽取模式 (`dd_search.py`)
- 重构采样循环：`draw()` 有放回 → `get_all_particles()` 全量遍历
- 权重开根号平滑（`w^0.5`）防止极端粒子一家独大
- 选牌从等权平均改为加权平均
- 新增 `_dd_eval_one_world()` 独立函数，代码清晰

#### 3. rank_bonus 削弱 (`dd_search.py`)
- `/50` → `/200`，K vs 2 差距从 0.22 墩降到 0.055 墩
- 修复防守方 K 被 rank_bonus 惩罚导致误选小牌的 bug
- 原则：平局裁决作用范围 ≤ 统计噪声 (0.5×SE)

#### 4. 叫牌约束三层架构 + 可视化 (`play_service.py`, `sampler.py`)
- 第一层：硬编码约束库（`bid_constraint_library.py`，正则匹配）
- 第二层：含义文本解析（`_parse_constraints_from_meanings()`，复用叫牌阶段 LLM 输出）
- 第三层：LLM 补充（仅前两层为空时触发，不额外消耗 API）
- 六引擎全部注入 `full_output["叫牌约束"]`，前端自动展示

#### 5. 前端改进
- **设置面板**: 粒子滑块按引擎显示，移除冗余"采样数"输入框，布局 nowrap 保证三列同行
- **打牌面板**: 出牌记录可折叠 (Collapse)，AI 输出始终可见；αμ 引擎标签显示 "αμ" 而非 "V4-Flash"
- **约束同步**: `bid_history` 改用 `seqStr`，`bid_meanings` 新增传递词牌含义文本

**修复的 Bug**:
- `_get_bid_constraints()` 返回 `None`（一二层产出约束后缺 return）
- `_alphamu_full_play` 未设置粒子数，共用 DD 的 200 粒子池
- `_mcts_play` 未显式设置粒子数（CLI 场景缺少 API 同步）
- `BELIEF_ALPHA_MU_PARTICLES` 漏导入
- 双层 Collapse 导致折叠按钮不可见
- SettingsPanel `flexWrap: wrap` 导致发牌设置区换行

**关键文件**: `dd_search.py`, `play_service.py`, `belief.py`, `config.py`, `SettingsPanel.jsx`, `PlayDetailPanel.jsx`, `useModelSettings.js`

## 2026-06-20

### 打牌引擎大师级优化（优先级 1-7 全套实施）

**背景**:
基于对 LLM / MCTS / DD / Tiered 四引擎的系统性评估，识别出阻碍达到大师级水平的 7 个优化方向。本次提交一次性落地优先级 1-7 全部改进，核心是修复 PIMC 的 strategy fusion 和 non-locality 缺陷，并强化信号体系、首攻融合、LLM 校验等专项能力。

**改进**:

#### 优先级 1：三信号关键决策检测（低成本，高收益）
- 重写 `_is_critical_decision`，从固定阈值改为三信号融合检测：
  - **Strategy Fusion 信号**：候选牌 min-max 跨度 ≥ `TIERED_FUSION_SPREAD`(3墩) → 不同分布下结果差异大
  - **集群信号**：候选牌按得分聚类，#1 与 #2 距离 > `TIERED_CLUSTER_SE`(2.0)×SE → 决策不确定
  - **样本不足信号**：有效样本 < `TIERED_MIN_SAMPLES`(30) → 统计不可靠
- 任一信号触发即升级 LLM 深度推理，避免 DD 在关键局面给出次优选择

#### 优先级 2：MCTS 根节点选牌 + rollout 策略强化
- 修复 MCTS 根节点选牌逻辑，按访问次数+胜率综合排序
- 强化 rollout 策略：`ROLLOUT_GREEDY_PROB`=0.80，80% 概率走启发式（赢墩/跟花色/弃牌），20% 随机探索
- MCTS 回退路径同样应用三信号检测（`_is_critical_decision_mcts`）

#### 优先级 3：信念状态跟踪 + 粒子滤波
- 新增 `bridge/mcts/belief.py`：粒子滤波器，维护 60 个加权粒子（possible worlds）
- 通过 void 约束（某家某花色已无牌）和防守信号更新粒子权重
- `BELIEF_SIGNAL_WEIGHT`=1.3（信号一致加权），`BELIEF_SIGNAL_PENALTY`=0.7（不一致降权）
- DD/MCTS 采样器接入 belief tracker，采样分布更贴近真实

#### 优先级 4：αμ 搜索（高成本，大师级核心）
- 新增 `bridge/mcts/alpha_mu.py`：实现 Wbridge5 的 αμ 搜索算法
- **核心数据结构**：
  - `OutcomeVector`：长度 N 的 0/1 向量（N=粒子数），表示各 possible world 下庄家方是否成约
  - `ParetoFront`：不被支配的向量集合，`add()` 自动去支配、`union()` 合并前沿
- **算法流程**：
  - Max 节点（庄家方）：所有候选 move 递归，front = 子 fronts 并集 → 强制所有 worlds 选同一 move（解决 strategy fusion）
  - Min 节点（防守方）：每个 world 独立选最小化 Max 的 move（假设完美信息，解决 non-locality）
  - 叶子节点：DDS `solve_board` 评估每个 world
- **触发条件**：每手 ≤8 张（`ALPHA_MU_ENDGAME_CARDS`），20 worlds，深度 ≤4，时间限制 8s
- 集成到 Tiered 引擎残局阶段，`tiered_phase: endgame_alpha_mu`

#### 优先级 5：首攻 DD + LLM 融合（中等成本）
- 新增 `_opening_lead_play`：首攻阶段并行跑 DD 蒙特卡洛（期望墩数 + min-max 区间）和 LLM（战略性首攻）
- LLM 拿到 DD 候选统计后做最终选择，复用 `_llm_play_with_dd_hint` 机制
- DD 不可用时回退纯 LLM 首攻

#### 优先级 6：防守信号模型（中等成本，防守专项）
- 新增 `bridge/mcts/signals.py`：编码三类防守信号
  - **Attitude**：高=欢迎/低=不欢迎（`BELIEF_SIGNAL_MIN_RANK`=8）
  - **Count**：张数信号（高/低暗示偶/奇张数）
  - **Suit Preference**：花色偏好信号
- `collect_all_signals` 从已完成墩和当前墩收集信号证据
- `format_partner_signals_for_prompt` 将同伴信号注入 LLM 防守提示词
- belief tracker 用信号约束过滤粒子分布

#### 优先级 7：LLM 输出校验层（低成本，稳定性）
- 新增 `bridge/mcts/llm_validator.py`：规则化校验 LLM 推荐出牌
  - 规则1：推荐牌必须在 `playable` 中（基本合法性）
  - 规则2：第四家"能赢却出小牌输墩"检测
  - 规则3：第二家"小牌盖大牌"错误检测
- 新增 `_validate_and_fallback`：校验失败时回退到 `_select_best_card`
- 校验器异常不阻塞主流程

**修改文件**:
- `bridge/mcts/alpha_mu.py` — 新增，αμ 搜索核心（OutcomeVector + ParetoFront + 递归搜索）
- `bridge/mcts/belief.py` — 新增，粒子滤波信念跟踪
- `bridge/mcts/signals.py` — 新增，防守信号模型（attitude/count/suit_preference）
- `bridge/mcts/llm_validator.py` — 新增，LLM 输出校验层
- `bridge/play_service.py` — 集成 αμ/首攻融合/信号注入/LLM 校验，新增 `_alpha_mu_play`、`_opening_lead_play`、`_validate_and_fallback`
- `bridge/mcts/dd_search.py` — 残局枚举阈值改为每手墩数
- `bridge/mcts/sampler.py` — 接入 belief tracker 和信号约束
- `bridge/mcts/search.py` — MCTS 根节点选牌逻辑修复
- `bridge/mcts/rollout.py` — rollout 策略强化（greedy_prob=0.80）
- `config.py` — 新增 αμ/信念/信号/Tiered 三信号参数
- `tests/test_alpha_mu.py` — 新增，αμ 算法测试（5 用例）
- `tests/test_belief_tracker.py` — 新增，信念跟踪测试
- `tests/test_signals_and_validator.py` — 新增，信号模型 + LLM 校验测试
- `tests/test_play_service_integration.py` — 新增，PlayService 全流程集成测试（15 用例）

**测试验证**:
- αμ 测试：5/5 通过（OutcomeVector 支配、ParetoFront 合并、残局端到端、DD 一致性、唯一选择）
- PlayService 集成测试：15/15 通过（初始化/首攻/中盘/残局αμ/撤销/完成判定/多引擎一致性）
- 端到端验证：残局场景 αμ 搜索 20 worlds、12 DDS calls、0.3s 完成搜索

**对打牌引擎的影响评估**:
- **LLM 引擎**：首攻阶段获得 DD 候选统计提示，防守阶段获得同伴信号注入，输出经规则校验。整体决策质量提升，违规出牌自动回退
- **MCTS 引擎**：根节点选牌更准确，rollout 策略更贴近实战，belief tracker 提供更真实的采样分布
- **DD 引擎**：残局阶段让位 αμ（≤8张），中盘阶段 belief tracker 改善采样分布，关键决策由三信号检测升级 LLM
- **Tiered 引擎**：残局阶段优先 αμ（解决 strategy fusion），不可用回退 DD 枚举（≤6张）；首攻阶段 DD+LLM 融合；中盘三信号检测升级 LLM
- **Perfect DD 引擎**：不受影响（全知双明手，无采样）

## 2026-06-15

### 截屏/图片识别全面优化

**背景**:
截屏识别存在三大问题：定约和首攻识别率低、部分页面 20 秒超时无响应、seed-2.0-lite 模型延迟 4.3s。

**改进**:

- **视觉提示词重构** (`llm/doubao_client.py`): 四项提取任务分区独立，手牌/叫牌/定约/首攻各有位置提示、格式要求和提取技巧。定约添加 4 个视觉位置线索，首攻明确区分"单独首攻牌"和"多张已打出牌"
- **模型切回 vision-pro** (`config.py`): `doubao-seed-2.0-lite` → `doubao-1.5-vision-pro`，延迟从 4.3s 降至 0.9s（快 5 倍）
- **宽松解析** (`api/main.py`): 识别阈值从"4 手各 13 张"降为"≥3 手即接受"，带警告信息返回而不阻塞。截屏后立即返回结果，不再死循环轮询 20s
- **跨手校验** (`api/main.py`): 新增每种花色四手合计 = 13 检测 + 重复牌张检测，能捕获模型花色错位
- **哈希防重处理** (`api/main.py`): 处理完截图立即更新哈希，同一张图不再重复发给模型

**配置**:
- 视觉模型: `DOUBAO_VISION_ENDPOINT` = `ep-20250404163138-bdvng` (doubao-1.5-vision-pro)

### 定约确认对话框 + 首攻输入

**改进**:
- 进入打牌前**始终弹出**确认对话框，预填识别到的定约/庄家/首攻
- 新增 X / XX 三按钮切换（— / X / XX）
- 新增首攻输入框（格式 `西:S5`），留空由 AI 决策
- `handleBeginPlay` 中首攻字符串 `"S5"` → `{suit, rank}` 格式修复

### 首攻信息贯通全链路

**改进**:
- **DF 格式输出**: `OutputFormatsRequest` 新增 `opening_lead`，识别到的首攻传入 `generate_deep_finesse_output`，DF 不再从首攻方手牌推算
- **保存/加载**: 4 处记录构造点新增 `board.opening_lead`，加载时恢复到 `imageOpeningLead`
- **DF 粘贴导入**: `CustomDealResponse` + `/api/custom-deal` 提取 DF 格式 `Lead:` + `OnLead:` 行组合为首攻

### 前端 UI 重构

**改进**:
- **Header 组件提取** (`web/src/components/layout/Header.jsx`): 标题栏桌面/移动端自适应，替代 50 行重复 JSX
- **按钮重分配**: 发牌/手动/图片/截屏按钮从 SettingsPanel 移至 CardTablePanel 内联；ControlButtons 移除发牌按钮
- **面板弹性宽度** (`web/src/styles/constants.js`): 新增 `PANEL_LAYOUT` 常量(minWidth 400 maxWidth 700 height 640)，面板从固定 600px 改为 flex 弹性
- **恢复丢失按钮** (`CardTable.jsx`): 清除牌局(DeleteSweep) + 检验定约 DF(GridOn) 按钮重新加入牌桌右上角，统一 IconButton + 暗色 Tooltip
- **开始页面简介**更新

### 花色颜色系统统一

**改进**:
- `suits.js` 集中管理：`getSuitColor(suit, isDark)` 亮色/暗色双套映射
- 暗色模式：♠♣ `#cbd5e1`(浅灰) ♥ `#f87171`(亮红) ♦ `#fb923c`(亮橙)
- 覆盖组件：CardTable / PlayPanel / PlayTable / PlayDetailPanel / HandDisplay
- `HandDisplay` 移除独立硬编码颜色（草花误用绿色 → 统一灰色），缺门 `-` 显示为对应花色半透明

### 研究模式

**改进**:
- 打牌中新增"研究模式"复选框
- 勾选后：庄家/明手不再强制绑定，任意位置独立切换 AI/人类
- 取消勾选：所有位置恢复 AI
- `doPlayInit` 中庄家/明手同步在研究模式下跳过

### 其他修复

- **上一墩残留清除**: 4 个新牌局入口 + `doPlayInit` 均清除 `lastCompletedTrick`
- **打牌详情暗色模式**: 出牌记录卡片背景/边框/hover、手牌 hover、位置标签全面适配
- **DF 格式 Lead 导出**: `generate_deep_finesse_output` 传入实际首攻替代推算

**修改文件**:
- `api/main.py` — 截屏哈希防重 + 宽松解析 + 跨手/重复校验 + 首攻全场贯通
- `bridge/play_service.py` — tiered_phase 存入 full_output
- `bridge/mcts/dd_search.py` — 残局阈值改为每手墩数
- `config.py` — DD_ENDGAME_CARD_THRESHOLD=4
- `llm/doubao_client.py` — VISION_PROMPT 重构 + vision-pro 端点
- `utils/screenshot.py` — 统一使用 VISION_PROMPT
- `web/src/App.jsx` — 定约对话框/首攻/研究模式/清除残留/简介
- `web/src/components/layout/Header.jsx` — 新增
- `web/src/components/CardTable.jsx` — 恢复按钮 + 花色颜色 + Tooltip 暗色
- `web/src/components/CardTablePanel.jsx` — 内联按钮 + 研究模式 checkbox
- `web/src/components/BiddingDetailPanel.jsx` — 面板弹性宽度 + 按钮始终可见
- `web/src/components/ControlButtons.jsx` — 移除发牌按钮
- `web/src/components/SettingsPanel.jsx` — 移除发牌/图片/截屏按钮
- `web/src/components/PlayDetailPanel.jsx` — tiered 阶段标签 + 全组件暗色适配
- `web/src/components/PlayPanel.jsx` — 花色颜色主题感知
- `web/src/components/PlayTable.jsx` — 花色颜色主题感知
- `web/src/components/HandDisplay.jsx` — 统一花色颜色 + 缺门半透明
- `web/src/constants/suits.js` — 主题感知双套颜色 + getSuitColor(isDark)
- `web/src/services/api.js` — getOutputFormats 加 openingLead 参数
- `web/src/styles/constants.js` — PANEL_LAYOUT 弹性布局常量
- `web/src/App.css` — 移动端叫牌表格字体增大
- `AGENTS.md` — 新增

## 2026-06-17

### Tiered 分层引擎重做：DD 替代 MCTS 中盘

**背景**:
v1.39 的 Tiered 引擎中盘使用 MCTS 树搜索，但 MCTS 在信息不完全条件下噪声大，采样效率不如 DD 蒙特卡洛。DD 每次求解 `solve_board` 可直接评估候选期望墩数。

**改进**:
- **中盘引擎从 MCTS 改为 DD** (`bridge/play_service.py`): 中盘阶段改用 DD 采样 + `solve_board`，速度快、统计更可靠
- **阶段简化** (5→4): 去掉"第一墩收尾"LLM 阶段，首攻→明手亮开→残局→中盘
- **残局阈值放宽**: `TIERED_ENDGAME_CARDS` 4→6，更早进入精确枚举
- **关键决策阈值收紧**: 庄家方 0.5→0.2，防守方 0.8→0.3（DD 统计比 MCTS 更可靠，阈值可更严格）
- **新增 `_llm_play_with_dd_hint()`**: 不确定时升级 LLM，注入 DD 候选信息，LLM 选择明显偏离 DD 最优时自动否决
- **移除 Hybrid 引擎**: 不再维护独立 hybrid 分支，Tiered 自动混合已覆盖
- **endplay 不可用回退**: 无 endplay 时自动回退 MCTS 路径
- **新增 `_is_critical_decision_mcts()`**: MCTS 回退路径的独立关键决策检测

**配置**:
- `TIERED_ENDGAME_CARDS`: 6 (原 4)
- `TIERED_CRITICAL_SPREAD_DECLARER`: 0.2 (原 0.5)
- `TIERED_CRITICAL_SPREAD_DEFENDER`: 0.3 (原 0.8)
- `TIERED_MIN_SAMPLES`: 30 — DD 有效样本少于此值不升级
- `TIERED_OVERRIDE_THRESHOLD`: 1.5 — LLM 与 DD 最优差超此墩数时否决 LLM

### Perfect DD 引擎 + 人类 DD 提示

**改进**:
- **`search_perfect()` 方法** (`bridge/mcts/dd_search.py`): 全知双明手搜索，AI 可访问四家完整手牌，一次 `solve_board` 得所有候选精确分
- **`/api/play/dd-hints` 端点** (`api/main.py`): 人类回合获取可选牌的完美 DD 提示（`+N`/`=`/`-N`），基于后台完整四家手牌
- **DD 提示默认开启** (`PlayDetailPanel.jsx`): `showDDHints` 默认 `true`，`localStorage` 持久化偏好，人类回合自动显示每张可选牌的 DD 预测
- 眼睛图标一键切换，所有引擎模式 (LLM/MCTS/DD/Tiered) 均可使用
- SettingsPanel 中 "完美DD (全知)" 引擎仅限发牌练习（AI 不应在模拟实战中获取未揭示手牌信息）

### 视觉识别深化

**改进**:
- **`parse_hand_with_suits()`** (`api/main.py`): 按花色符号 (♠♥♦♣) 解析手牌，正确保留缺门花色用 `-` 占位，不再粗暴删除花色符号导致缺门丢失
- **图片压缩** (`llm/doubao_client.py`): 长边 >1920px 等比缩至 1920，转 JPEG quality 85%，大幅减少传输量
- VISION_PROMPT: 明确要求缺门用 `-` 占位，四花色必须全部列出

### 前端多项改进

- **校验警告展示** (`App.jsx`): 新增 `warning` 状态，图片/截屏识别后的校验警告显示为黄色 Alert
- **编辑叫牌对话框**: 📋 按钮预填叫牌序列文本，支持 `(位置)叫品-` 格式解析
- **手牌编辑**: 🖊 按钮预填当前手牌（带花色符号格式），编辑后走相同解析流程
- **首攻重置**: 首攻解析失败后可重新输入
- **定约解析增强**: 支持 `4HX`/`4HXX` 内联加倍格式

**修改文件**:
- `api/main.py` — dd-hints 端点 + parse_hand_with_suits + perfect 引擎 + 耗时日志
- `bridge/play_service.py` — tiered 重做 (DD 中盘) + perfect + _llm_play_with_dd_hint + 否决机制
- `bridge/mcts/dd_search.py` — search_perfect 全知双明手
- `config.py` — 新阈值/配置项
- `llm/doubao_client.py` — 图片压缩 + VISION_PROMPT + timeout
- `web/src/App.jsx` — warning/编辑/首攻重置/手牌编辑/定约解析
- `web/src/components/PlayDetailPanel.jsx` — DD 提示默认开启 + localStorage 持久化
- `web/src/components/CardTable.jsx` — 花色颜色 + Tooltip
- `web/src/components/SettingsPanel.jsx` — perfect 引擎限制
- `web/src/services/api.js` — getDDHints API

## 2026-06-14

### 分层打牌引擎 (Tiered Play Engine)

**背景**:
现有四种打牌引擎(LLM/MCTS/DD/Hybrid)互斥，用户选一个从头用到尾。但不同引擎在不同阶段各有所长：首攻需要LLM战略推理，中盘MCTS快速免费，关键决策需LLM深度思考，残局DD枚举精确。

**改进**:
- 新增第5种引擎模式 `"tiered"`，自动根据局面阶段选择最优引擎
- **首攻** (LEAD) → LLM深度思考：防守方花色选择、将牌策略
- **明手亮开** (DUMMY_REVEAL) → LLM深度思考：庄家全局做庄规划
- **第一墩收尾** (len(tricks)==0) → LLM深度思考：第三家防守判断 + 庄家首次执行
- **中盘** → MCTS快速搜索 + 关键决策检测
- **关键时刻** → 自动升级LLM（MCTS候选分差≤阈值 或 定约岌岌可危）
- **残局** (≤4张/人) → DD精确枚举所有分布 + solve_board
- 庄家/防守方不对称阈值：庄家0.5墩（MCTS可靠，少升级），防守0.8墩（噪声大，多升级）
- 升级时显示MCTS分析结果和升级原因

### DD引擎残局精确枚举

**改进**:
- `DDSearch._enumerate_endgame()`: 剩余未知牌≤10张时枚举所有分布替代随机采样
- 每组分布调用solve_board求精确期望值，消除采样方差
- 枚举数估算超限时自动回退采样
- 构造器新增 `endgame_card_threshold` / `max_enumerations` 参数

**配置**:
- 分层引擎: `TIERED_CRITICAL_SPREAD_DECLARER`=0.5, `TIERED_CRITICAL_SPREAD_DEFENDER`=0.8, `TIERED_ENDGAME_CARDS`=4
- DD枚举: `DD_ENDGAME_CARD_THRESHOLD`=10, `DD_ENDGAME_MAX_ENUMERATIONS`=5000

### Bug修复

- **记录持久化丢失**: `useBridgeRecords.saveRecord` 中 localStorage 写入在React updater外部，并发模式下变量未赋值即跳过。移入updater内部修复
- **出牌错误信息丢失**: 后端 `success=false` 时未填 `error` 字段，前端仅检查 `result.error`。修复后透传具体原因（如"必须跟♠"）
- **模拟实战角色切换禁用**: 打牌面板内手牌未知时角色切换被禁（条件4），删除该限制；`showInput`条件缺少 `!showPlayPanel` 导致叫牌输入框拦截打牌手牌输入
- **打牌手牌输入需两次提交**: `handleSetPlayHand` 未同步前端 `hands` 状态，导致 `showInput` 抢占渲染

### 前端改进

- 分层引擎支持模型/深度思考设置
- AI出牌显示耗时（ms/s），覆盖所有引擎
- Tiered橙色徽章 + tiered_phase显示
- 打牌详情面板支持tiered引擎MCTS柱状图

**修改文件**:
- `bridge/play_service.py` — LLM路径提取为`_llm_play()`，新增`_tiered_play()`、`_is_critical_decision()`
- `bridge/mcts/dd_search.py` — 新增`_enumerate_endgame()`枚举方法
- `config.py` — 分层引擎 + DD枚举配置
- `api/main.py` — tiered路由 + 耗时统计 + 出牌错误透传
- `web/src/components/SettingsPanel.jsx` — Tiered菜单项
- `web/src/components/PlayDetailPanel.jsx` — Tiered徽章 + 耗时显示
- `web/src/components/CardTable.jsx` — 角色切换/手牌输入修复
- `web/src/hooks/useBridgeRecords.js` — localStorage持久化修复
- `web/src/App.jsx` — 耗时记录 + 出牌错误提示 + 手牌同步

**测试**:
- `test_tiered_engine.py` — 阶段判定 + DD枚举 + 关键决策检测验证通过

---

## 2026-05-03

### DD打牌引擎方向反转Bug修复

**背景**:
DD引擎（蒙特卡洛+DDS双明手）打牌效果差，柱状图上不同出牌赢墩数完全相同或极端偏差，等于随机出牌。根因是`solve_board`返回值的赢墩方向被误判。

**改进**:
- `solve_board`返回的是`deal.curplayer`（当前出牌人）所在方的赢墩数，而非`deal.first`（领出者）。修复后用`PLAYER_TO_POSITION`映射`deal.curplayer`来判断方向，第2/4家时不再反转
- Rank偏置修复：防守方`-(avg+rank_bonus)`替代`-(avg-rank_bonus)`，正确偏好小牌保留实力
- score_map key加固：显式映射`_DENOM_TO_SUIT/_RANK_TO_CHAR`替代`.abbr`，消除对`use_unicode`全局设置的静默依赖
- 柱状图防守方`avg_tricks`逆序排列，让最优出牌排最前
- `state_utils.py`新增`PLAYER_TO_POSITION`反向映射

**修改文件**:
- `bridge/mcts/dd_search.py` — solve_board方向修复 + rank偏置 + key加固 + 逆序
- `bridge/mcts/state_utils.py` — 新增PLAYER_TO_POSITION

**测试验证**:
- `test_solve_board.py`验证`solve_board`返回值方向确认
- MCTS约束测试9/9全部通过
- DD/Hybrid模式打牌验证效果良好

---

## 2026-05-05

### 逼局进程强制规则（提示词修复）

**背景**:
北家持♠J53 ♥AKQJT7 ♦K4 ♣95（14点），叫牌序列1C-X-1H-P-2C，联手26-29点已确定进局。AI选择2♥（6-10点止叫），严重叫弱。根因是备用提示词的逼局进程段(C段)没有约束"不得选择不逼叫的示弱叫品"。

**改进**:
- 备用提示词"叫品筛选过程"C段新增**逼局进程强制规则**：禁止选择简单重叫自己花色、简单加叫队友最低花色、pass等不逼叫的示弱叫品
- 必须选择逼叫性叫品保持进程开放：跳叫新花 > 第四花色逼局 > 扣叫 > 2NT(逼叫) > 其他强制逼局约定叫品
- 示例：1♣-X-1♥-P-2♣后应叫2♦人工逼局或3♥逼局邀请，不应叫2♥

**修改文件**:
- `llm/prompts.py` — C段新增逼局进程强制规则
- `bidding-cases/2026-05-01/case-033.json` — 新增案例记录

---

### 叫牌细节面板布局重构

**背景**:
叫牌细节面板顶部区域与按钮行功能分散，记录下拉框独立在标题栏右侧，"简单"checkbox与记录下拉框混排，"切换到打牌"按钮在内容区单独一行。

**改进**:
- 记录下拉框移至按钮行左侧，与"开始/暂停/撤销/保存/切换到打牌"等按钮同行
- 切换到打牌按钮从细节模式内容区移除，合并到按钮行右侧
- "简单"checkbox右对齐到标题栏
- 简单模式下记录下拉框置灰禁用，不再消失
- 细节模式内容区拖动条从外层移至内层内容容器，按钮行固定不滚动

**修改文件**:
- `web/src/components/BiddingDetailPanel.jsx` — 布局重构

---

### 系统模式统一：positionRoles 重构

**背景**:
`humanPosition` 和 `positionRoles` 双向同步造成状态冗余，练习/模拟模式判断散落在各组件中，checkbox 逻辑不一致。

**改进**:

**A. 状态统一**
- 删除 `humanPosition` 状态，全系统统一用 `positionRoles`（`{'南':'ai'|'human', ...}`）
- 删除 `isNewDeal` 状态，按钮文字改用 `!biddingStarted && biddingSequence.length === 0` 判断
- 新建 `web/src/utils/position.js`：`isHumanPosition`、`hasAnyHuman`、`getHumanPositions`、`getPartnerPosition`
- 旧记录兼容：加载时自动将 `human_position` 迁移为 `position_roles`
- 发牌时自动设置所有位置为 AI（旁观模式）

**B. 四人叫牌位置约束**
- 合法状态：4AI（全旁观）、1H+3AI（单人练习）、3H+1AI（模拟实战）、4H（全手动）
- 2H+2AI 自动修正：点 AI→人类 切换人类位置，点人类→AI 切换 AI 位置
- 1H+3AI 练习模式：显示"队友手牌"+"对方手牌" checkbox
- 3H+1AI 模拟实战模式：AI 手牌始终显示，不显示 checkbox（其他三家无手牌）
- 4H 全手动模式：所有位置显示"未知"，手动输入叫品

**C. 双人叫牌方向**
- 删除 SettingsPanel 中的练习方向选择器
- 方向由发牌人位置自动推断：南/北→NS，东/西→EW
- `addBid` 中对手方自动 pass 改用 `practiceDirection`

**D. Checkbox 清理**
- 删除 `showAIHands` checkbox
- 统一为"队友手牌"+"对方手牌"两个 checkbox
- 叫牌阶段：全 AI 旁观或 3H+1AI 模拟实战时隐藏
- 打牌阶段："庄家手牌"（庄家是 AI 时显示）+"显示已出"（始终显示）

**E. 清除手牌 → 模拟实战**
- 按钮 tooltip 从"清除所有手牌"改为"模拟实战"，图标从 DeleteSweep 改为 PlayArrow
- 清除手牌后自动设置 positionRoles 为 `{南:'ai', 北:'human', 东:'human', 西:'human'}`，重置 checkbox

**F. 手牌可见性统一**
- `CardTable.shouldShowHandContent(position)` 统一处理所有手牌显示逻辑
- 叫牌阶段：全AI 显示所有手牌；人类练习基于 checkbox；模拟实战 AI 始终显示
- 打牌阶段：明手始终可见；庄家受 checkbox 控制；人类位置始终可见自己的手牌
- AI 无手牌位置显示输入框，Human 无手牌位置显示"未知"

**G. 双人模式无打牌**
- 双人模式隐藏"切换到打牌"按钮（`gameMode !== 'pair'`）
- pair 模式下不显示打牌相关控件

**H. 保存完整性**
- 所有保存路径保留 `practice_direction` 和 `position_roles`
- 修复 `saveCompletePlayRecord` 依赖数组缺少 `practiceDirection` 的 bug
- 修复 `bidding_complete` 自动保存缺少 `practice_direction` 字段的 bug

**修改文件**:
- `web/src/App.jsx` — 状态统一、位置约束、模拟实战、保存完整性
- `web/src/utils/position.js` — 新建位置工具函数
- `web/src/components/CardTablePanel.jsx` — checkbox 统一、模拟实战隐藏
- `web/src/components/CardTable.jsx` — `shouldShowHandContent` 统一
- `web/src/components/BiddingDetailPanel.jsx` — 双人模式隐藏打牌按钮
- `web/src/components/SettingsPanel.jsx` — 移除练习方向选择器
- `web/src/components/BiddingControls.jsx` — humanPosition→positionRoles

---

### AI提供商选择器移除

**背景**:
AI提供商选择器（DeepSeek/Doubao切换）已不再需要。

**改进**:
- SettingsPanel移除AI提供商下拉框及关联的备用模型条件显示
- App.jsx移除aiProvider状态、syncAIProvider、handleAIProviderChange
- useGameSettings移除aiProvider相关状态和方法
- api.js移除getAIProvider/setAIProvider导出

**修改文件**:
- `web/src/components/SettingsPanel.jsx`
- `web/src/App.jsx`
- `web/src/hooks/useGameSettings.js`
- `web/src/services/api.js`

---

### 叫牌控制面板暗色背景适配

**背景**:
暗色模式下叫牌控制面板的按钮背景仍为浅色系（灰白底色），"简单重叫自己花色"、加倍等按钮的背景格外刺眼。

**改进**:
- `getBidColor` 函数增加 `isDark` 参数，暗色下统一返回黑灰背景(`#1e293b`)白色文字(`#e2e8f0`)
- 叫牌控制面板、JF面板、定约结果卡片（绿色/蓝色）背景全面暗色适配
- JF关键字颜色暗色适配

**修改文件**:
- `web/src/components/BiddingControls.jsx`

---

### 系统标题与按钮栏合并

**背景**:
"桥牌练习系统"标题占一整行，下面按钮（发牌/设置/历史等）再占一行，浪费垂直空间。

**改进**:
- 桌面版和手机版标题与ControlButtons合并到同一行
- 移除多余的 `Divider`

**修改文件**:
- `web/src/App.jsx`

---

### 加载历史记录出牌失败修复

**背景**:
从历史记录加载未完成的打牌后，点击确认出牌提示"出牌失败"。根因是前端恢复了 `playState` 但后端打牌服务未同步初始化，调用 `playCard` 时后端状态为空。

**改进**:
- `handleStartPlay` 从记录加载时，先调 `playInit` 初始化后端打牌服务
- 初始化成功后重放已有出牌（已完成墩+当前墩），使后端状态与历史记录一致
- 初始化失败不阻断前端显示，仅打warning日志

**修改文件**:
- `web/src/App.jsx` — handleStartPlay 增加 playInit + 重放逻辑

---

### 打牌详情面板输入模式滚动条修复

**背景**:
切换到"输入"模式时，外层容器和内部提示词框都有滚动条，页面出现双滚动条。

**改进**:
- 输入模式下外层容器设 `overflow: 'hidden'`，仅保留内部提示词框滚动条
- 输出模式不受影响

**修改文件**:
- `web/src/components/PlayDetailPanel.jsx` — 外层容器 overflow 条件判断

---

## 2026-05-02

### 叫牌操作按钮迁移至叫牌细节面板

**背景**:
叫牌操作按钮（开始叫牌、暂停/继续、撤销、保存）位于顶部 ControlButtons 区域，和系统级操作（发牌、历史记录、设置等）混在一起。打牌面板已有独立的按钮行，叫牌面板也需要统一。

**改进**:
- BiddingDetailPanel 新增按钮行（开始/重新叫牌、暂停/继续、撤销、保存），右对齐
- ControlButtons 移除叫牌相关按钮，仅保留系统级操作（发牌、设置、历史记录、API、约定、暗色模式）
- 按钮文字简化：`开始叫牌→开始`，`继续叫牌→继续`，`停止叫牌→暂停`
- 叫牌暂停时开始按钮隐藏，只显示"继续"
- 暂停按钮切换为"继续"后 `disabled={stopBidding && aiThinking}`，AI未返回不可继续

**修改文件**:
- `web/src/components/BiddingDetailPanel.jsx` — 新增按钮行、props
- `web/src/components/ControlButtons.jsx` — 移除叫牌相关按钮和props
- `web/src/App.jsx` — 更新两组件props传递

---

### 已保存未完成打牌加载后继续按钮修复

**背景**:
未打完的牌局保存后加载，切换到打牌界面时，"继续"按钮不显示。原因是显示条件 `(!isHumanTurn || isStartOfTrick)` 在人类玩家回合且非每墩首张时全不满足。

**改进**:
- "继续"按钮条件增加 `isHistoryRecord` 分支：从历史加载时始终显示，不受回合限制
- 用户点击"继续"后恢复正常的打牌流程

**修改文件**:
- `web/src/components/PlayDetailPanel.jsx` — 继续按钮条件增加 isHistoryRecord

---

### 加载完整叫牌后重新叫牌不自动开始

**背景**:
导入完整叫牌记录后点击"重新叫牌"，之前会直接调用 `startBidding()` 自动开始叫牌。对于人类发牌人的场景，用户需要先看到叫牌控制面板再开始。

**改进**:
- `resetBidding` 移除 `startBidding()` 调用，改为重置状态后显示"开始"按钮
- `startBidding` 中发牌人是人类时同步 `setShowBiddingControls(true)`，确保控制面板出现
- 重新叫牌后的行为和新发牌完全一致

**修改文件**:
- `web/src/App.jsx` — resetBidding 移除自动 startBidding，startBidding 增加 human turn 控制面板显示

---

### humanPosition 与 positionRoles 状态同步修复

**背景**:
`humanPosition` 初始值为 `null`，从不与 `positionRoles` 同步。`loadRecordToTable` 只恢复 `humanPosition` 不恢复 `positionRoles`。导致发牌人是人类时无法正确识别回合。

**改进**:
- 新增 `useEffect` 监听 `positionRoles` 自动同步到 `humanPosition`
- `loadRecordToTable` 从 `humanPosition` 推导并恢复 `positionRoles`
- 移除 `handlePositionRoleChange` 中的重复同步代码，由 effect 统一管理

**修改文件**:
- `web/src/App.jsx` — 同步 effect、loadRecordToTable 恢复 positionRoles、移除重复同步

---

### 记录类型枚举重构

**背景**:
原有记录类型只有 `in_progress` 和 `complete` 两种，无法区分叫牌进行中、打牌进行中、仅叫牌完成、全部完成等不同状态。历史记录标签也经常误标（如无打牌数据却显示"叫牌+打牌"）。

**改进**:
- 4种新类型：`bidding_in_progress`、`play_in_progress`、`bidding_complete`、`play_complete`
- 历史记录标签：叫牌进行中 / 打牌进行中 / 仅叫牌完成 / 打牌完成
- 兼容旧记录：有 `play.state` 或 `play.tricks` 数据时正确判断为有打牌数据

**修改文件**:
- `web/src/App.jsx` — 4个保存点的 type 更新 + 历史标签显示逻辑

### 添加主动保存进度功能

**背景**:
之前只有叫牌/打牌完成后的自动保存，没有进行中的手动保存。用户希望能在叫牌或打牌过程中保存进度，导入后继续。

**功能设计**:
1. **记录类型统一**:
   - `in_progress`: 进行中（叫牌中或打牌中）
   - `complete`: 完成（叫牌完成或打牌完成）

2. **覆盖保存逻辑**:
   - 每个牌局通过 `sourceRecordId` 关联
   - 保存时优先覆盖同 `sourceRecordId` 的记录
   - 重新叫牌/重新打牌不重置 `sourceRecordId`，继续覆盖同一记录
   - 新发牌时重置 `sourceRecordId`，创建新记录

3. **手动保存按钮**:
   - 叫牌进行中显示"保存"按钮
   - 点击后保存当前叫牌进度到历史记录

4. **导入后继续**:
   - 导入进行中记录后，`sourceRecordId` 指向原记录
   - 继续叫牌后保存会覆盖原记录

**修改文件**:
- `web/src/hooks/useBridgeRecords.js` — `saveRecord` 支持 `sourceRecordId` 覆盖逻辑
- `web/src/App.jsx` — 添加 `currentRecordId` 状态、手动保存逻辑、自动保存添加 `sourceRecordId`
- `web/src/components/ControlButtons.jsx` — 添加"保存"按钮

---

## 2026-05-02

### 修复四人模式相继pass判断bug

**背景**:
四人模式下，当一家搭档两人相继pass后，后续该家两个位置自动pass。但代码在判断"搭档最近一次pass"时，没有排除第一个实质性叫牌之前的pass，导致错误触发。

**问题场景**:
叫牌序列 `(东)pass-(南)1D-(西)pass-(北)1H-(东)?`
- 东的第一次pass在1D之前（开叫前pass）
- 西在1D之后pass
- 代码错误地认为东西已相继pass，导致东自动pass

**根因**:
找搭档pass的循环遍历整个序列，没有跳过第一个实质性叫牌之前的pass。

**修复**:
- 新增 `firstRealBidIndex` 变量，记录第一个实质性叫牌的位置
- 找搭档pass时，跳过索引小于 `firstRealBidIndex` 的pass
- 确保只考虑第一个实质性叫牌之后的pass才算"放弃叫牌"

**修改文件**:
- `web/src/App.jsx` — 相继pass判断逻辑增加 `firstRealBidIndex` 过滤

---

## 2026-05-01

### DeepSeek V4 非思考模式显式禁用修复

**背景**:
用户关闭"深度思考"开关后，叫牌和打牌速度完全没有提高。根因是 DeepSeek V4 的 thinking 模式默认为 `enabled`——之前的代码在 `thinking=False` 时没有传 `thinking` 参数，API 默认进入思考模式，产生大量 `reasoning_tokens`，响应时间与深度思考模式完全相同。一晚上多次修改（JSON mode 开关、timeout 调整、thread pool 超时处理）都没找到根因。

**改进**:
- `chat_json()` 和 `chat()` 方法在非思考模式下显式传入 `extra_body={"thinking": {"type": "disabled"}}`
- 日志中 `reasoning_tokens=0` 确认思考模式已正确关闭

**效果**:
- 叫牌（Flash 非思考）：14-19s（之前思考模式需 60-90s）
- 打牌（Flash 非思考）：6-9s（之前思考模式需 30-78s）
- Flash 非思考 vs Flash 思考：速度提升约 3-5 倍

**修改文件**:
- `llm/deepseek_client.py` — `chat()` 和 `chat_json()` 方法增加 `thinking: disabled` 逻辑

---

### 打牌流程全面重构

**背景**:
打牌交互流程存在多处逻辑问题：角色切换不能立即生效、墩首/墩中/墩完成的行为不一致、暂停/继续按钮在特定场景不显示或显示错误、明手角色切换无效。需要从根本上重新设计打牌流程的状态机和交互逻辑。

**核心设计原则**:

1. **前端 `positionRoles` 作为角色判断的唯一真相源** — 不再依赖后端 `playState.is_human_turn`，所有人类/AI判断从前端 `positionRoles` 即时计算，确保角色切换后UI立即响应。

2. **三个关键状态变量**：
   - `playInitiated`：打牌已启动（点击"开始"或重新打牌AI首攻后），区别于 `playStarted`（第一张牌打出后）
   - `isPlayPaused`：暂停状态，暂停时显示"继续"按钮、启用角色切换
   - `playStarted`：第一张牌已打出，"撤销"按钮依赖此状态

3. **每墩生命周期**：
   - **墩首**（`current_trick.cards.length === 0`）：显示"继续"按钮（即使领出者是人类），隐藏选牌面板。点击"继续"后：人类→显示选牌面板；AI→自动出牌。
   - **墩中**（`current_trick.cards.length > 0 && < 4`）：人类回合自动暂停并显示选牌面板；AI回合自动出牌。
   - **墩完成**（`current_trick.cards.length === 4`）：自动暂停，保存最后一墩信息。

**具体改进**:

1. **人类回合判断函数 `isCurrentPlayerHuman()`**（App.jsx）:
   - 读取前端 `positionRoles` 而非后端 `playState.is_human_turn`
   - 桥牌规则：当前玩家为明手（dummy）时，检查庄家（declarer）的角色
   - PlayDetailPanel 中同步计算 `isHumanTurn`，保证UI即时响应

2. **AI自动出牌 Effect**（App.jsx）:
   - 前置条件：`showPlayPanel && playState && !playAiLoading && !playLoading && !isPlayPaused && playInitiated`
   - 非人类回合且未结束时，延迟500ms自动调用 `handleAIPlay()`
   - 依赖数组包含 `positionRoles`，角色切换后立即重新评估

3. **人类回合自动暂停 Effect**（App.jsx）:
   - 墩首跳过（`!isStartOfTrick`），由"继续"按钮控制
   - 墩中人类回合自动设置 `isPlayPaused = true`

4. **墩完成检测 Effect**（App.jsx）:
   - 通过 `prevTricksCountRef` 比对墩数变化
   - 墩数增加→保存最后一墩信息→自动暂停
   - 打牌完成（phase === 'complete'）→自动保存完整打牌记录

5. **角色切换按钮禁用条件**（CardTable.jsx）:
   ```
   禁用条件 = showPlayPanel && playInitiated && (!isPlayPaused || aiLoading)
              && !(isStartOfTrick && !aiLoading)
   ```
   - 未开始打牌：始终启用
   - 暂停状态 + 非AI加载中：启用
   - 墩首 + 非AI加载中：启用（允许人类领出者切换为AI）
   - AI思考中（`aiLoading`）：禁用（防止并发冲突）
   - AI自动出牌中（未暂停）：禁用

6. **开始/继续/暂停/撤销按钮逻辑**（PlayDetailPanel.jsx）:
   - **"开始"按钮**：`!isComplete && !playInitiated` — 打牌前显示
   - **"继续"按钮**：`!isComplete && playInitiated && isPaused && (!isHumanTurn || isStartOfTrick)` — 墩首（含人类领出者）或AI回合暂停时显示；AI加载中时 disabled
   - **"暂停"按钮**：`!isComplete && playInitiated && !isPaused && !isHumanTurn` — AI自动出牌时可手动暂停
   - **"撤销"按钮**：`(!isComplete && playStarted && isPaused) || (isComplete && !isHistoryRecord)` — 暂停时或完成后（非历史记录）可撤销；AI加载中时 disabled

7. **选牌面板显隐逻辑**（PlayDetailPanel.jsx）:
   ```
   隐藏条件（优先级从高到低）：
   1. isComplete → "打牌已结束"
   2. !playInitiated || (isPaused && isStartOfTrick) → 隐藏（等待点击开始/继续）
   3. isPaused && !isHumanTurn → 隐藏（AI回合暂停，显示继续按钮）
   4. !isHumanTurn → 隐藏（AI正在思考）
   ```

8. **庄家/明手角色双向同步**（App.jsx `handlePositionRoleChange`）:
   - 切换庄家→同步更新明手角色
   - 切换明手→同步更新庄家角色
   - 原因：桥牌规则中庄家替明手打牌，两者角色必须一致
   - 同步通过 `setPositionRoles` 立即生效（前端），再异步调用 `updatePlayPlayerRoles` 更新后端

9. **墩首人类→AI切换自动暂停**（App.jsx `handlePositionRoleChange`）:
   - 墩首切换领出者从人类到AI后，自动设置 `isPlayPaused = true`
   - 显示"继续"按钮，点击后AI自动出牌
   - 保证用户在角色切换后有确认机会

**修改文件**:
- `web/src/App.jsx` — 新增 `isCurrentPlayerHuman()`、重写3个打牌Effect、重写 `handlePositionRoleChange`（庄家/明手同步 + 墩首人类→AI暂停）
- `web/src/components/PlayDetailPanel.jsx` — 选牌面板显隐逻辑重构、按钮显隐/禁用条件重构、`isHumanTurn` 从 `positionRoles` 即时计算、明手出牌提示（"X家替明手Y家出牌"）
- `web/src/components/CardTable.jsx` — 角色切换Toggle禁用条件重构（新增 `playInitiated` prop、`isStartOfTrick` 例外）
- `web/src/components/CardTablePanel.jsx` — 传递 `playInitiated`、`positionRoles` 到子组件

**测试验证**: Vite build 通过，无编译错误。需在实际叫牌+打牌流程中端到端验证各场景。

---

## 2026-04-29

### 修复主提示词pass叫品误触发fallback的问题

**背景**:
当预处理结果中包含pass选项（如"花色开叫"片段中的`pass：以上没有合适叫品`），LLM选择pass后，`_is_no_valid_bid`方法会继续检查筛选过程中是否包含"无合格叫品"关键词。由于LLM输出具有随机性，有时在描述pass选择时会使用"无合格叫品"这样的措辞，导致系统误判为没有合格叫品而切换到备用提示词，JF约定从"花色开叫"错误地变为"成局与满贯"。

**根因分析**:
- 主提示词约定：无合格叫品时输出`"JF无合格叫品"`；pass是合法叫品时输出`"pass"`
- `_is_no_valid_bid`在`bid="pass"`时仍检查筛选过程中的"无合格叫品"关键词
- LLM描述随机性导致同一场景有时切换fallback有时不切换

**改进**:
- `_is_no_valid_bid`方法增加判断：当`bid="pass"`时直接返回`False`，不再检查筛选过程
- 主提示词路径添加verbose模式调试日志，记录关键字提取、预处理结果和决策路径
- fallback各分支添加路径追踪日志（no jf_content / not structural / no subsequent bids）

**修改文件**:
- `bridge/bidding_service.py` — `_is_no_valid_bid`增加pass直接返回False逻辑；`ai_bid`添加verbose调试日志

**测试验证**: API测试确认`(南)pass-`后西家开叫位置正确返回`JF约定: 花色开叫`，不再误切换到`成局与满贯`

---

## 2026-04-18

### 暗色模式全面适配

**背景**:
系统此前未做暗色模式适配，大量组件使用硬编码的白色/浅灰背景和深色文字，在暗色模式下显示异常（白底在深色主题中刺眼，浅灰文字不可见）。

**改进**:
- **手牌面板（HandDisplay）**: 标题颜色、卡片背景、花色符号颜色、HCP标签、人类/队友手牌渐变背景及边框暗色适配
- **牌桌面板（CardTablePanel）**: 面板背景色、标题"当前牌局"/"打牌阶段"文字颜色暗色适配
- **叫牌细节面板（BiddingDetailPanel）**: 全部硬编码白色背景→深色半透明；代码块`#f8f9fa`/`#fafafa`→深色；`#666`文字→浅色；`#ddd`/`#e0e0e0`边框→深色
- **打牌详情面板（PlayDetailPanel）**: AI输出卡片背景、模型标签、代码块、出牌卡片选中/禁用态、已完成墩行背景、庄家方/防守方/"需要"统计面板暗色适配
- **牌桌中心（CardTable）**: 叫牌表格文字/标题栏/格子背景暗色适配；出牌区域空位占位框/已出牌卡片/hover态暗色适配
- **双明手表格（DoubleDummyTable）**: 表头文字、分隔线、单元格文字及背景暗色适配；统一"-"与定约方块样式
- **打牌交互（PlayPanel/PlayTable）**: 出牌选择卡片三态暗色适配；人类出牌区/墩数统计面板暗色适配；hover高亮色适配
- **绿色牌桌背景暗色调整**: `#2e7d32→#1b5e20` 改为 `#1a3a1c→#0d1f0f`；中心面板白色→深蓝灰
- **主题切换开关移出设置面板**: 从SettingsPanel中移除Switch，改为顶部按钮栏最右端☀/🌙图标按钮

**修改文件**:
- `web/src/components/HandDisplay.jsx` — 全部硬编码颜色改为`isDark`条件分支
- `web/src/components/CardTable.jsx` — 四家手牌外框、牌桌中心出牌区域、叫牌表格暗色适配
- `web/src/components/CardTablePanel.jsx` — 面板背景和标题暗色适配
- `web/src/components/BiddingDetailPanel.jsx` — 白色/浅灰/代码块/边框暗色适配
- `web/src/components/PlayDetailPanel.jsx` — AI输出卡片/代码块/统计面板/出牌卡片暗色适配
- `web/src/components/PlayPanel.jsx` — 出牌选择区/卡片/统计面板暗色适配
- `web/src/components/PlayTable.jsx` — 出牌位置/卡片/统计面板暗色适配
- `web/src/components/DoubleDummyTable.jsx` — 全部硬编码颜色暗色适配
- `web/src/components/ControlButtons.jsx` — 新增暗色模式图标按钮
- `web/src/components/SettingsPanel.jsx` — 移除暗色模式Switch
- `web/src/App.css` — `.bidding-cell`样式合并、`.card-table-container`暗色渐变
- `web/src/App.jsx` — 传递`darkMode`/`onToggleDarkMode`到ControlButtons

**测试验证**: Vite HMR实时更新无编译错误；暗色模式下所有面板、卡片、表格、文字均清晰可见

---

### 打牌系统多项增强与Bug修复

**背景**:
打牌模块存在多个关键Bug和体验问题，包括将牌将吃无法识别赢墩、全局规划字段缺失、有将/无将策略未区分、出牌交互不佳等。

**Bug修复**:

1. **将牌将吃无法识别赢墩** (`bridge/play_types.py`):
   - 问题：`Contract.from_str()` 解析定约字符串时 `suit` 保存为英文代码（如 `H`），但 `Card.suit` 使用中文符号（如 `♥`），导致 `Trick.winner()` 中 `card.suit == self.trump` 永远为 `False`
   - 影响：将牌将吃不会被识别为赢墩，将牌相关逻辑全部失效（清将判断、跟花色判断等）
   - 修复：在 `Contract.from_str()` 中将英文花色代码 `S/H/D/C` 转换为中文符号 `♠/♥/♦/♣`，与 `Card.suit` 保持一致

**功能增强**:

2. **全局规划字段显示** (`web/src/components/PlayDetailPanel.jsx`):
   - 问题：前端输出字段列表缺少"全局规划"字段
   - 修复：在 `fields` 数组中添加"全局规划"字段（青色 `#00838f`，多行显示），"后续路线建议"也改为多行显示

3. **有将定约数输墩 vs 无将定约数赢墩** (`llm/prompts.py`):
   - 将"计算赢墩与失墩"部分分为两种模式：
   - **有将定约**：按输墩评估清单5步（逐花色输墩→汇总对比→消除手段扫描→清将时机→安全验证）
   - **无将定约**：按赢墩规划五问（快速赢墩→哪个花色补足→危险方→忍让策略→后备方案）
   - 输出格式"全局规划"字段同步分为有将/无将两种模板

4. **打牌按钮交互重构** (`web/src/App.jsx`, `web/src/components/PlayDetailPanel.jsx`, `web/src/components/BiddingDetailPanel.jsx`):
   - 叫牌面板"开始打牌"按钮改名为"切换到打牌"
   - 点击"切换到打牌"后只切换到打牌状态，不自动开始
   - 打牌面板新增开始/暂停/继续三态按钮（第一张牌打出后显示暂停）
   - 重新打牌按钮从顶部移到开始/暂停/继续旁边，右对齐，统一 `outlined` 风格
   - 打牌结束后隐藏开始/暂停/继续按钮，只保留重新打牌
   - 新增 `playInitiated` 状态区分"已点击开始"和"已出第一张牌"
   - 重新打牌后不再切回叫牌界面，AI首攻则自动开始，人类首攻则等待出牌

5. **人类出牌交互优化** (`web/src/components/PlayDetailPanel.jsx`):
   - 取消"出牌"确认按钮
   - 第一次点击牌选中，再次点击同一张牌确认出牌
   - 提示文字动态显示"点击选择"或"再次点击确认"

**修改文件**:
- `bridge/play_types.py` — Contract.from_str() 花色代码转中文符号
- `llm/prompts.py` — 有将/无将策略分离、输墩评估清单、赢墩规划五问
- `web/src/App.jsx` — playInitiated 状态、handleResetPlay 重构、按钮逻辑
- `web/src/components/PlayDetailPanel.jsx` — 全局规划字段、按钮三态、出牌交互
- `web/src/components/BiddingDetailPanel.jsx` — "切换到打牌"按钮改名

---

### 打牌提示词准确性加强

**背景**:
AI在打牌推理中出现多个概念性错误，需要加强提示词的关键概念定义和出牌位置策略。

**问题与修复**:

1. **连张概念误判** (`llm/prompts.py`):
   - 问题：AI把KJ称为"连张"，误用01首攻规则从KJ75中攻J
   - 修复：首攻规则开头增加"连张 vs 间张"概念澄清
     - 连张(Sequence)：大牌相邻连续，如KQJ、QJT、JT9
     - 间张：大牌之间有间隔，如KJ、AQ，**不是连张**
     - 中间连张：首攻牌之下紧挨着有牌，如KJ10（J10相邻）、AJ10
     - 直接点名常见错误：KJ75既没有连张也没有中间连张
   - 首攻示例增加反例：`KJ75 | 5 | KJ不是连张！长四首攻`、`AQ754 | 4 | AQ不是连张！长四首攻`
   - 首攻表格注释加强：攻J前提是J10相邻，KJ后面没有10时不适用
   - 首攻规则条目细化："有连张大牌攻大牌" → "攻连张中最顶上的一张（如KQJ攻K，QJT攻Q）"

2. **第四家出牌误判** (`llm/prompts.py` + `bridge/play_service.py`):
   - 问题：AI在第四家位置时猜测"如果后面还有人出更大的牌"
   - 修复：新增"出牌位置策略"规则
     - 第一家：选择攻击方向
     - 第二家：防守方遵守"首攻与信号"部分的规定
     - 第三家：防守方遵守"首攻与信号"部分的规定（优先盖过前两家，盖不过时考虑信号）
     - 第四家：**你之后不再有人出牌！** 用能赢的最小牌赢墩或出最小牌
   - 新增模板变量：`play_position`（第几家出牌）、`current_trick_count`（当前墩已有牌数）、`remaining_players`（你之后还有几家未出牌）
   - 全局局面新增"本墩出牌位置"信息行

3. **领出者误认** (`llm/prompts.py` + `bridge/play_service.py`):
   - 问题：AI看到"(南)♠5"却认为"北家首攻♠5"，混淆领出者
   - 修复：墩记录格式增加领出者标注
     - 已完成墩：`第1墩[领出:南]: (南)♠5 (西)♠2 (北)♠A (东)♠8 - 赢家: 北`
     - 当前墩：`[领出:南] (南)♠5 (西)♠2`
     - 空墩：`尚未开始（你是本墩领出者）`

4. **领出信号误判** (`llm/prompts.py`):
   - 问题：AI把领出的小牌解读为"不欢迎信号"（如北家赢墩后领出♠4被解读为姿态信号）
   - 修复：信号定义部分增加关键说明
     - **信号仅适用于跟牌，领出时不存在信号！**
     - 不能把领出的小牌解读为"不欢迎信号"

**修改文件**:
- `llm/prompts.py` — 连张定义、出牌位置策略、信号适用范围、领出者标注
- `bridge/play_service.py` — 出牌位置计算、墩记录格式化（领出者标注、play_position变量）

---

### 打牌提示词重大修改

**背景**:
原打牌提示词（`PLAY_SYSTEM_PROMPT`）结构简单，缺少关键信息，AI出牌决策质量不佳。需要重新设计提示词，增强AI对牌局的理解能力。

**改进**:

1. **提示词全面重写** (`llm/prompts.py`):
   - 新增模板变量：`{bidding_sequence}`（叫牌过程）、`{trick_number}`（当前墩数）、`{side}`（庄家方/防守方）、`{declarer_remaining}`（庄家还需墩数）、`{defender_remaining}`（防守方还需墩数）、`{trump_cleared}`（将牌是否清完）、`{defense_signals_section}`（防守信号体系）、`{played_cards_info}`（已见牌张与花色轮次）
   - 新增"已见牌张与花色轮次"信息区，帮助AI推断剩余大牌位置
   - 新增"防守信号体系约定"条件区（仅防守方出牌时提供）
   - 新增"庄家分析逻辑"7步框架（赢墩计算→输墩计算→读防守→时效性→联通与进手→安全打法→终局打法）
   - "推理过程"从隐含改为必须显式输出的字段
   - 输出格式全面升级：`推理过程`、`立场分析`、`推荐出牌`、`核心逻辑`、`备选方案`（数组）、`备选逻辑差异`、`风险提示`、`后续路线建议`

2. **输出Schema更新** (`llm/deepseek_client.py`):
   - `PLAY_SCHEMA` 字段从旧格式更新为新格式
   - 必填字段：`推理过程`、`立场分析`、`推荐出牌`、`核心逻辑`
   - 新增字段：`备选方案`（数组类型）、`备选逻辑差异`、`风险提示`、`后续路线建议`

3. **打牌服务增强** (`bridge/play_service.py`):
   - `get_ai_play` 方法：新增6个格式变量计算和注入
   - 新增 `_format_played_cards_info(state)`: 按花色统计已出/未见牌张，生成逐花色摘要
   - 新增 `_check_trump_cleared(state)`: 检查将牌是否已全部清出（区分庄家方/防守方剩余将牌）
   - 新增 `_format_defense_signals(state, current_player)`: 返回防守信号体系约定文本（姿态信号、张数信号、花色选择信号、首攻约定）
   - 结果解析更新：适配新的字段名（`推理过程`、`立场分析`、`备选方案`、`后续路线建议`等）

**修改文件**:
- `llm/prompts.py` — 全面重写 `PLAY_SYSTEM_PROMPT`
- `llm/deepseek_client.py` — 更新 `PLAY_SCHEMA`
- `bridge/play_service.py` — 新增3个辅助方法，更新提示词格式化和结果解析

---

### 前端：移除重复的叫牌记录管理逻辑

**问题**:
`App.jsx` 中存在两处与自定义 Hook 完全重复的逻辑：
1. `useBiddingState` hook 已抽取叫牌状态管理，但 App.jsx 未使用，直接用 `useState` 重新声明了所有状态
2. `useBiddingRecords` hook 已抽取叫牌记录持久化管理，但 App.jsx 未使用，内联重写了所有函数
3. `isBiddingComplete` 函数在 App.jsx 和 hook 中各有一份（App.jsx 版本更完整）

**改进**:

1. **App.jsx 使用 `useBiddingState` hook** 替代内联的叫牌状态声明（`biddingSequence`, `currentBidder`, `aiBiddingHistory` 等15个状态），删除 App.jsx 中的重复 `isBiddingComplete` 定义
2. **App.jsx 使用 `useBiddingRecords` hook** 替代内联的叫牌记录管理（`biddingRecords`, `loadBiddingRecords`, `saveBiddingRecord` 等6个状态+9个函数），删除约140行重复代码
3. **更新 `useBiddingState` hook**：
   - `isBiddingComplete` 逻辑更新为与 App.jsx 一致的完整版本（支持3个连续pass检测）
   - `resetBidding` 移除 `setDealer` 调用（dealer 不在 hook 管理范围），重命名为 `initBiddingState`
   - `startBidding` 重命名为 `markBiddingStarted`（App.jsx 中的 `startBidding` 包含更多业务逻辑）
   - `toggleStopBidding` 重命名为 `toggleStopBiddingState`
4. **更新 `useBiddingRecords` hook**：
   - `exportRecords` 支持无选中时导出全部记录（与 App.jsx 行为一致）
   - `importRecords` 添加去重逻辑和文件格式校验
   - 移除 `loadRecordToTable`（它依赖 App 级别的状态设置函数）
5. **App.jsx 中保留的业务逻辑函数**：`startBidding`（手牌验证+完整初始化）、`resetBidding`（调用 `initBiddingState`）、`clearAllHands`、`loadRecordToTable`

**修改文件**:
- `web/src/App.jsx` — 删除约170行重复代码，使用两个 hook
- `web/src/hooks/useBiddingState.js` — 更新逻辑匹配 App.jsx
- `web/src/hooks/useBiddingRecords.js` — 更新逻辑匹配 App.jsx

---

## 2026-04-13 (晚间)

### 打牌阶段UI优化

**背景**:
打牌阶段进入后，左右面板和牌桌中心区域有多处UI不一致和可优化之处。

**改进**:

1. **右侧记录下拉框切换时面板位置跳动** (`web/src/components/BiddingDetailPanel.jsx`):
   - 问题：从"控制"切换到"细节"时，记录下拉框出现导致顶部栏变高，白色面板位置下移
   - 修复：将下拉框用 `opacity + pointerEvents` 控制显隐（替代条件渲染），隐藏时仍占据空间
   - 顶部栏 `minHeight` 设为 40，确保始终有足够空间

2. **左右面板顶部栏高度统一** (`web/src/components/CardTablePanel.jsx`, `PlayDetailPanel.jsx`):
   - 左侧 `CardTablePanel` 顶部栏 `minHeight` 从 32 改为 40
   - 右侧 `PlayDetailPanel` 顶部栏 `minHeight` 从 32 改为 40
   - 与右侧 `BiddingDetailPanel` 一致

3. **左侧标题颜色与右侧统一** (`web/src/components/CardTablePanel.jsx`):
   - 标题 Typography variant 从 `subtitle1` 改为 `h6`，与右侧 PlayDetailPanel 一致

4. **打牌状态下右侧墩数标签移入白色面板** (`web/src/components/PlayDetailPanel.jsx`):
   - "庄家方"、"防守方"、"需要"三个标签和"继续"按钮从灰色区域移入白色面板内部顶部

5. **四家手牌与中间面板间距统一** (`web/src/components/CardTable.jsx`):
   - 南北手牌与中间面板间距从 `8px` 逐步减小到 `0`，使四边间距视觉一致
   - 手牌框 boxShadow 从 `0 4px 12px rgba(0,0,0,0.15)` 缩小为 `0 2px 6px rgba(0,0,0,0.12)`

6. **牌桌中心文字和旋转控件优化** (`web/src/components/CardTable.jsx`):
   - 中心文字（"X家出牌"、"X赢"）字体从 `0.65rem` 增大到 `0.85rem`
   - AI出牌旋转进度条从文字侧面改为叠加在文字上（绝对定位居中）
   - 旋转控件尺寸从 10px 增大到 22px，颜色改为深色半透明 `rgba(0,0,0,0.45)`

**修改文件**:
- `web/src/components/BiddingDetailPanel.jsx`
- `web/src/components/CardTablePanel.jsx`
- `web/src/components/PlayDetailPanel.jsx`
- `web/src/components/CardTable.jsx`

---

## 2026-04-13

### 打牌模块代码清理与优化

**背景**:
打牌过程模块刚完成，代码中遗留大量DEBUG日志、重复逻辑和死代码。网页版响应慢，需要清理优化。

**改进**:

1. **移除DEBUG print语句**（后端4个文件，约16处）:
   - `play_engine.py`: 移除 `[DEBUG PlayEngine.play_card]` print
   - `play_types.py`: 移除 `[DEBUG Trick.to_dict]` 和 `[DEBUG PlayState.play_card]` print
   - `play_service.py`: 移除 3 处 `[DEBUG get_ai_play]` print
   - `api/main.py`: 移除约 10 处 `[DEBUG]` print（叫牌、打牌、状态查询）
   - 这些DEBUG语句在生产环境中每次请求都会输出，影响性能和日志可读性

2. **修复死代码和冗余逻辑** (`bridge/play_types.py`):
   - 移除 `PlayState.__post_init__` 中 NT/非NT 的重复分支（两种情况执行相同代码）
   - 移除未使用的 `_get_right_hand()` 方法
   - 修复 `PlayEngine.get_visible_hands()` 中搭档手牌可见性判断的死代码（`pass` 分支无效果）

3. **修复 play_card API 端点 bug** (`api/main.py`):
   - 问题：`trick_complete` 判断检查 `state.current_trick.is_complete()`，但出牌完成后一墩已被归档、`current_trick` 已重置为空，永远返回 `False`
   - 修复：通过比较出牌前后的墩数（`len(state.tricks)`）来判断是否刚完成一墩
   - 同时修复 `trick_winner` 的取值：新一墩的首攻者就是上一墩的赢家

4. **提取 API 重复代码为辅助函数** (`api/main.py`):
   - `_format_bidding_sequence()`: 统一叫牌序列格式化（原来在 image/screenshot/clipboard 3处重复）
   - `_parse_vision_hands()`: 统一视觉识别结果解析（原来在 image/clipboard 2处重复）
   - `_hands_to_response_dict()`: 统一手牌字典转换（原来在 custom-deal 等 4+处重复）
   - 将 `import re/traceback/tempfile/os` 移到文件顶部，消除约 15 处内联 import

5. **前端提取共享常量** (`web/src/constants/suits.js` - 新增):
   - `SUIT_SYMBOLS`: 花色符号映射
   - `SUIT_COLORS`: 花色颜色映射（按花色名）
   - `SUIT_COLOR_MAP`: 花色颜色映射（按符号）
   - `getSuitColor()`: 辅助函数
   - `PlayPanel.jsx`、`PlayTable.jsx`、`PlayDetailPanel.jsx` 改为 import 共享常量

6. **消除 CardTable 重复渲染逻辑** (`web/src/components/CardTable.jsx`):
   - 提取 `renderCenterContent()` 函数，合并桌面版和手机版完全重复的 30+ 行 DoubleDummyTable/出牌状态/叫牌过程渲染代码

**修改文件**:
- `bridge/play_types.py`
- `bridge/play_engine.py`
- `bridge/play_service.py`
- `api/main.py`
- `web/src/constants/suits.js` (新增)
- `web/src/components/PlayPanel.jsx`
- `web/src/components/PlayTable.jsx`
- `web/src/components/PlayDetailPanel.jsx`
- `web/src/components/CardTable.jsx`

**本地恢复点**: `backups/backup_20260412_233741/`

---

## 2026-04-11

### 前端代码结构优化 - 自定义Hooks与组件提取

**背景**:
App.jsx 文件过大（约1900行），包含大量状态管理和重复代码。需要提取自定义 hooks 和组件来简化代码结构，提高可维护性。

**改进**:

1. **提取自定义 Hooks** (`web/src/hooks/`):
   - `useBiddingRecords.js`: 管理叫牌记录相关状态和函数
   - `useGameSettings.js`: 管理游戏设置相关状态和函数
   - `useBiddingState.js`: 管理叫牌状态相关状态和函数
   - `useDoubleDummy.js`: 管理双明手分析相关状态和函数
   - `useOutputFormats.js`: 管理输出格式相关状态和函数

2. **提取设置面板组件** (`web/src/components/SettingsPanel.jsx`):
   - 将设置面板从 App.jsx 中提取为独立组件
   - 包含叫牌设置和发牌设置两组
   - 减少约57行代码

3. **统一样式常量** (`web/src/styles/constants.js`):
   - 创建样式常量文件，包含面板样式、按钮样式、排版样式等
   - 便于后续统一管理和复用

4. **清理未使用导入**:
   - 移除 `CardTable`、`BiddingControls`、`BiddingTable`、`AIOutputPanel` 等未使用的组件导入

5. **手机版 JF 约定面板优化**:
   - JF 约定面板固定高度：手机版 500px，网页版 400px
   - 内容超出时显示滚动条
   - 叫牌控制按钮使用自适应 grid 布局，修复溢出问题

**修改文件**:
- `web/src/hooks/useBiddingRecords.js` (新增)
- `web/src/hooks/useGameSettings.js` (新增)
- `web/src/hooks/useBiddingState.js` (新增)
- `web/src/hooks/useDoubleDummy.js` (新增)
- `web/src/hooks/useOutputFormats.js` (新增)
- `web/src/components/SettingsPanel.jsx` (新增)
- `web/src/styles/constants.js` (新增)
- `web/src/App.jsx`
- `web/src/components/BiddingDetailPanel.jsx`
- `web/src/components/BiddingControls.jsx`

**测试验证**: 桌面版和手机版功能正常，JF 约定面板显示滚动条，叫牌控制按钮无溢出。

---

### 手机版叫牌过程框优化

**背景**:
手机版叫牌过程框宽度不足，NT 等叫品显示不全。发牌人用红色显示后，"*" 号显得多余。

**改进**:
1. **叫牌过程框宽度增加**: 从 42% 增加到 50%，NT 等叫品可完整显示
2. **移除发牌人"*"号**: 叫牌过程框中发牌人已用红色显示，不再需要"*"号标识
3. **手牌框宽度保持不变**: 手牌框保持 42% 宽度，避免溢出

**修改文件**:
- `web/src/components/BiddingTable.jsx`
- `web/src/components/CardTable.jsx`

**测试验证**: 手机版叫牌过程框显示完整，手牌框无溢出。

---

### 前端组件结构优化

**背景**:
前端代码经过多次迭代，积累了一些重复代码和未使用的样式。桌面版和手机版的控制按钮代码几乎相同，App.css中也有很多未使用的样式。

**改进**:
1. **提取公共组件** (`web/src/components/ControlButtons.jsx`):
   - 创建 `ControlButtons` 组件，合并桌面版和手机版的控制按钮
   - 通过 `size` prop 控制按钮大小和显示文本
   - 减少约100行重复代码

2. **清理CSS样式** (`web/src/App.css`):
   - 删除未使用的样式：`hand-card`、`llm-output-panel` 等
   - 保留正在使用的样式：`card-table-container`、`bidding-table` 等
   - 减少约150行冗余CSS

**修改文件**:
- `web/src/components/ControlButtons.jsx` (新增)
- `web/src/App.jsx`
- `web/src/App.css`

**测试验证**: 桌面版和手机版控制按钮功能正常，界面显示无变化。

---

### 删除手机版面板拖拽排序功能

**背景**:
手机版面板拖拽排序功能使用频率低，增加了代码复杂度。用户反馈该功能用处不大，决定删除以简化代码。

**改进**:
1. **删除组件** (`web/src/components/MobileDraggableContainer.jsx`):
   - 删除整个拖拽排序组件
   - 删除 SortableItem 子组件

2. **简化手机版布局** (`web/src/App.jsx`):
   - 移除 MobileDraggableContainer 和 SortableItem 包装
   - 移除 panelOrder 状态和 localStorage 存储
   - 直接渲染当前牌局和叫牌细节面板

3. **删除依赖** (`web/package.json`):
   - 删除 @dnd-kit/core
   - 删除 @dnd-kit/sortable
   - 删除 @dnd-kit/utilities

**修改文件**:
- `web/src/components/MobileDraggableContainer.jsx` (删除)
- `web/src/App.jsx`
- `web/package.json`

**测试验证**: 手机版界面正常显示，面板顺序固定为当前牌局在上、叫牌细节在下。

---

## 2026-04-09

### 阻击叫牌体系参数传递优化

**背景**:
用户可以选择不同的阻击叫牌体系（自然阻击 vs 多功能/麦德伯格），但该参数之前只传递给叫牌序列分析功能，没有传递给AI叫牌提示词，导致AI无法根据所选体系做出正确的叫牌决策。

**改进**:
1. **提示词参数扩展** (`llm/prompts.py`):
   - 在 `BIDDING_SYSTEM_PROMPT`、`BIDDING_FALLBACK_PROMPT`、`HUMAN_BID_PROMPT` 三个提示词中添加 `{deal_system}` 占位符
   - 明确说明"我方使用的是xxx阻击叫牌体系"，指导AI根据所选体系选择叫品

2. **参数传递完善** (`bridge/bidding_service.py`):
   - `ai_bid` 方法：传递 `deal_system` 到 `BIDDING_SYSTEM_PROMPT.format()`
   - `_fallback_bid` 方法：添加 `deal_system` 参数并传递到 `BIDDING_FALLBACK_PROMPT.format()`
   - `human_bid` 方法：传递 `deal_system` 到 `HUMAN_BID_PROMPT.format()`
   - 所有调用 `_fallback_bid` 的地方都传递 `deal_system` 参数

3. **叫牌序列分析优化** (`bridge/bidding.py`):
   - 开叫位置关键字选择：根据阻击叫牌体系选择"花色开叫"或"花色开叫1"
   - 支持新增的"花色开叫1"JF约定片段，专门用于多功能/麦德伯格体系

4. **输出显示增强**:
   - 后端返回结果添加"阻击叫体系"字段
   - 前端叫牌细节面板显示"阻击叫体系"信息

5. **代码清理**:
   - 删除 `explain_bid` 方法（v1.27添加，叫牌建议功能的一部分）
   - 删除 `build_bid_history` 方法（v1.27添加，叫牌建议功能的一部分）
   - 删除 `EXPLAIN_BID_PROMPT` 提示词（v1.27添加）

**修改文件**:
- `llm/prompts.py`
- `bridge/bidding_service.py`
- `bridge/bidding.py`
- `web/src/App.jsx`
- `web/src/components/AIOutputPanel.jsx`

**测试验证**: 选择"多功能/麦德伯格"体系后，开叫位置正确使用"花色开叫1"片段，叫牌细节显示所选体系。

---

### 发牌人调整逻辑优化

**背景**:
用户反馈在叫牌过程中点击"停止叫牌"后，应该能够调整发牌人。同时，调整发牌人后应该重置叫牌状态，回到发牌后的初始状态。

**改进**:
1. **停止叫牌后可调整发牌人** (`web/src/components/CardTable.jsx`):
   - 修改判断条件：`!biddingStarted || stopBidding` 时允许调整
   - 添加 `stopBidding` prop 到组件

2. **调整发牌人时重置叫牌状态** (`web/src/App.jsx`):
   - `biddingStarted` → false
   - `stopBidding` → false
   - `isNewDeal` → true
   - 叫牌序列清空
   - AI叫牌历史清空
   - 已pass的AI位置清空

**修改文件**:
- `web/src/App.jsx`
- `web/src/components/CardTable.jsx`

**测试验证**: 停止叫牌后可以点击方位标签调整发牌人，调整后界面回到初始状态（按钮显示"开始叫牌"，停止/继续叫牌按钮消失）。

---

## 2026-04-07

### 移除叫牌建议功能

**背景**:
叫牌建议功能与练习模式功能重叠，且用户反馈练习模式已能满足需求。为简化代码和用户体验，决定移除叫牌建议功能。

**改进**:
- 移除"练习/建议"模式切换按钮
- 删除 `BiddingSuggestion.jsx` 组件
- 移除 `getBiddingSuggestion` API函数
- 移除后端 `/api/bidding-suggestion` 端点
- 保留练习模式和JF约定片段功能

**修改文件**:
- `web/src/App.jsx`
- `web/src/services/api.js`
- `web/src/components/BiddingSuggestion.jsx`（删除）
- `api/main.py`

---

### UI优化：发牌人设定、叫牌控制切换、输出格式修复

**背景**:
1. 发牌人设定方式不够直观，需要改进交互方式
2. 叫牌细节标签的控制/细节切换位置不固定，影响用户体验
3. 人类叫牌时叫品含义显示不正确（显示pass含义而非实际叫品含义）
4. 叫牌结束后检验定约按钮无法点击

**改进**:

1. **发牌人设定功能重构** (`web/src/App.jsx`, `web/src/components/CardTable.jsx`):
   - 去掉顶部下拉框，改为点击方位标签设定发牌人
   - 使用"*"代替"(发)"作为发牌人标记
   - 叫牌过程中禁止修改发牌人（点击无响应，光标不变）

2. **叫牌细节标签切换优化** (`web/src/App.jsx`):
   - 标题始终显示"叫牌细节"
   - 切换按钮始终显示，叫牌结束时禁用
   - "简单"复选框和记录选择器始终在右侧显示

3. **当前牌局框切换优化** (`web/src/App.jsx`):
   - 切换按钮改为"叫牌过程/小房子"
   - 字体加大到0.875rem
   - AI手牌checkbox移动到最右端

4. **叫牌含义不匹配问题修复**（关键修复）:
   
   **问题描述**：用户点击叫牌按钮叫了3S，但叫牌含义显示的是pass的含义。
   
   **问题分析**：
   - 后端日志显示 `human_bid` 收到的 `user_input=pass` 而不是 `3S`
   - 根本原因：`addBid` 函数使用旧的 `humanPosition` 状态判断当前叫牌者是否是人类
   - 但系统已经改用 `positionRoles` 来管理每个位置的角色（`{南: 'human', 北: 'ai', ...}`）
   - 导致 `isCurrentHuman` 判断为 false，人类叫牌时没有调用 `humanBid` API
   - 结果：叫牌序列正确更新为3S，但没有获取叫牌含义，显示的是之前pass的含义
   
   **修复方案**：
   - `addBid` 函数：将判断逻辑从 `humanPosition === currentBidder` 改为 `positionRoles[currentBidder] === 'human'`
   - `human_bid` 方法：在所有返回路径添加"完整叫牌序列"字段
   - `fetchOutputFormats` 函数：将 `humanPosition` 参数改为 `positionRoles`
   
   **修改文件**:
   - `web/src/App.jsx`（`addBid` 函数判断逻辑）
   - `bridge/bidding_service.py`（`human_bid` 方法返回值）
   - `web/src/App.jsx`（`fetchOutputFormats` 参数）

**修改文件**:
- `web/src/App.jsx`
- `web/src/components/CardTable.jsx`
- `bridge/bidding_service.py`

**Git提交**: `71b5033`

**本地恢复点**: `backups/backup_20260407_004004/`

---

## 2026-04-06

### 叫牌建议功能

**背景**:
用户需要一个叫牌建议功能：提供一手牌和当前叫牌序列，AI给出叫牌建议。该功能模拟实战场景：三个人类玩家和一个AI玩家的叫牌过程，AI需要判断人类叫牌的含义，并决定自己的叫牌。

**核心设计讨论**:

1. **叫牌历史构建问题**:
   - 练习叫牌时，AI根据手牌+序列+JF约定决定叫品，系统自动记录含义
   - 叫牌建议时，用户输入叫牌序列，AI需要推断每个叫品的含义
   - 问题：`subsequent_bids` 包含的是"当前可选叫品"，不是"历史叫品含义"
   - 解决：创建 `explain_bid()` 函数，先从JF约定匹配，匹配不到则调用AI解释

2. **叫牌建议与练习叫牌的关系**:
   - 本质相同：都是人类和AI混合叫牌的过程
   - 区别：练习叫牌最多1个人类，叫牌建议固定3个人类+1个AI
   - 未来目标：支持人类和AI在四个位置任意配置

3. **发牌人推断**:
   - 第一个叫品的位置就是发牌人，无需单独选择
   - `dealer = biddingSequence[0].position`

4. **叫牌含义提取策略**（关键决策）:
   - 优先从 `subsequent_bids` 匹配叫品含义（前提是实战叫牌正确）
   - 如果 `subsequent_bids` 为空或不包含实战叫品，调用AI解释
   - AI调用参数：已叫牌序列、实战叫品、JF约定片段
   - 这是用户最终确认的实现方向

5. **模式选择讨论**:
   - 讨论：是否现在就合并练习叫牌和叫牌建议？
   - 决策：先做好独立模式，测试验证后再考虑合并
   - 理由：独立模式需验证，合并有风险，待收集反馈后再决定

**实现内容**:

1. **新增提示词** (`llm/prompts.py`):
   - `EXPLAIN_BID_PROMPT`: 在不知道手牌的情况下解释叫品含义
   - 输入：叫牌序列、待解释叫品、JF约定内容
   - 输出：简洁的叫品含义描述

2. **新增方法** (`bridge/bidding_service.py`):
   - `explain_bid()`: 解释某个叫品在当前序列下的含义
     - 优先从 `subsequent_bids` 匹配叫品含义
     - 匹配不到则调用AI解释
   - `build_bid_history()`: 从叫牌序列构建叫牌历史
     - 逐步解析叫牌序列
     - 为每个叫品调用 `explain_bid()`
     - 累积叫牌历史

3. **更新接口** (`api/main.py`):
   - `BiddingSuggestionRequest` 新增 `dealer` 参数
   - `/api/bidding-suggestion` 调用 `build_bid_history()` 构建叫牌历史
   - 将叫牌历史传给 `ai_bid()` 生成建议

4. **前端组件** (`web/src/components/BiddingSuggestion.jsx`):
   - 截屏识别手牌和叫牌序列
   - 双模式手牌输入（文本/点选花色）
   - 叫牌序列编辑（下拉选择叫品）
   - 发牌人自动从第一个叫品位置推断
   - 建议结果显示（默认叫品+可展开完整分析）

5. **API客户端** (`web/src/services/api.js`):
   - `getBiddingSuggestion()` 新增 `dealer` 参数

6. **模式切换** (`web/src/App.jsx`):
   - 新增"练习"和"建议"模式切换按钮
   - 练习模式：原有叫牌练习功能
   - 建议模式：叫牌建议功能

**修改文件**:
- `llm/prompts.py`
- `bridge/bidding_service.py`
- `api/main.py`
- `web/src/components/BiddingSuggestion.jsx`
- `web/src/services/api.js`
- `web/src/App.jsx`

**技术要点**:
- `hcp` 是 `@property` 属性，不是方法，应使用 `hand.hcp` 而非 `hand.hcp()`
- 叫牌建议流程：`build_bid_history()` → `set_bid_meanings()` → `ai_bid()`

**未来规划**:
- 统一练习叫牌和叫牌建议的架构
- 支持人类和AI在四个位置任意配置
- 逐步输入模式：用户依次输入叫牌，实时显示含义

---

## 2026-04-05

### 历史记录删除确认逻辑

**改进**:

1. **删除记录时检查注释** (`web/src/App.jsx`):
   - 删除前检查选中记录是否包含注释
   - 有注释时弹出确认对话框，显示注释数量
   - 无注释时直接删除，无需确认
   - 防止误删有价值的注释记录

**修改文件**:
- `web/src/App.jsx`

---

### 历史记录多选导出导入 + AI详细输出记录

**改进**:

1. **历史记录多选功能** (`web/src/App.jsx`):
   - 每条记录前添加复选框，支持多选
   - 点击记录行即可选择/取消选择
   - 选中记录高亮显示
   - 全选/取消全选按钮

2. **导出导入增强** (`web/src/App.jsx`):
   - 导出时可选导出部分记录（选中时只导出选中的）
   - 导入支持多条记录合并，自动去重
   - 导出文件包含完整 `aiBiddingHistory` 数组

3. **AI详细输出记录** (`web/src/App.jsx`):
   - 每条记录保存AI叫牌的 `full_output`（手牌分析、叫牌历史、叫品筛选过程）
   - 通过"加载"功能可查看完整AI输出

4. **操作按钮统一** (`web/src/App.jsx`):
   - 移除每条记录单独的按钮
   - 所有操作按钮集中在底部
   - 加载/编辑注释：仅选中1条时可用
   - 删除：选中≥1条时可用，显示数量

5. **截图功能改进** (`utils/screenshot.py`, `api/main.py`):
   - 直接触发系统截图工具（Win+Shift+S）
   - 5秒延迟后自动读取剪贴板
   - 简化用户操作流程

6. **FormData上传修复** (`web/src/services/api.js`):
   - 移除多余的 `Content-Type: multipart/form-data` header
   - 让浏览器自动设置正确的boundary

7. **新增叫牌案例** (`bidding-cases/`):
   - case-029：6-5双高套竞争叫牌（Pass过于保守）
   - case-030：竞争叫牌中跳叫自己花色过于激进

8. **新增Skill** (`.trae/skills/bridge-bidding-recorder/`):
   - 叫牌案例记录skill，支持手动激活记录案例

**修改文件**:
- `web/src/App.jsx`
- `web/src/services/api.js`
- `utils/screenshot.py`
- `api/main.py`
- `bidding-cases/cases-index.json`
- `bidding-cases/2026-04-02/case-029.json`
- `bidding-cases/2026-04-03/case-030.json`
- `.trae/skills/bridge-bidding-recorder/`

**Git提交**: `55a8b1a`

**本地恢复点**: `backups/backup_20260405_102835/`

---

## 2026-03-28

### 设置面板重构 + 图片发牌文件上传

**改进**:

1. **设置面板分组重构** (`web/src/App.jsx`):
   - 将设置面板分为"叫牌设置"和"发牌设置"两个独立组
   - 两组之间用竖线 (`Divider`) 分隔，布局更清晰
   - 叫牌设置：模式、发牌人、人类位置、备用模型
   - 发牌设置：发牌方式、自定义、图片、截屏按钮

2. **按钮样式统一** (`web/src/App.jsx`):
   - 字体大小统一为 `0.875rem`（与下拉框一致）
   - 边框颜色统一为 `rgba(0, 0, 0, 0.23)`
   - 高度统一为 `40px`，内边距统一
   - 移除文字大写转换 (`textTransform: 'none'`)

3. **图片发牌改为文件上传** (`web/src/App.jsx`, `web/src/services/api.js`, `api/main.py`):
   - 前端：添加"浏览..."按钮，使用文件选择器选取图片
   - API服务：使用 `FormData` 上传文件
   - 后端：使用 `UploadFile` 接收文件，保存到临时目录处理后自动清理
   - 解决浏览器安全限制导致的文件路径问题
   - 依赖：安装 `python-multipart` 包支持文件上传

---

### 右侧面板合并重构（桌面版 + 手机版）

**背景**: 将叫牌控制、JF约定面板、叫牌细节合并为统一右侧面板，根据叫牌状态智能切换显示内容。

**改进**:

1. **桌面版右侧面板重构** (`web/src/App.jsx`):
   - 删除原 `showAIBiddingOutput` 条件分支的双布局结构
   - 删除原第二行独立的 `BiddingControls` 组件
   - 统一为单一 Paper（750px），根据叫牌状态切换：
     - **人类回合（叫牌进行中）**：上部显示叫牌控制，下部显示JF约定片段（flex:1，可滚动）
     - **AI回合（叫牌进行中）**：切换显示叫牌细节（可随时查看AI叫牌过程）
     - **叫牌结束**：显示叫牌细节
     - **观察者模式**（humanPosition=null）：`showAIBiddingOutput` 开关仍有效，控制是否显示叫牌细节

2. **手机版面板重构** (`web/src/App.jsx`):
   - `biddingDetails` 面板改为统一面板，与桌面版相同的切换逻辑
   - `biddingControls` 面板隐藏（return null），叫牌控制已整合到 biddingDetails
   - 人类回合时面板高度自适应（auto + minHeight:500px），叫牌细节时固定400px

3. **BiddingControls 组件扩展** (`web/src/components/BiddingControls.jsx`):
   - 新增 `hideJFPanel` prop（默认 false）
   - 当 `hideJFPanel=true` 时不渲染 JF约定 Paper，便于父组件独立控制 JF约定面板位置



### 双明手分析Bug修复 + 备份系统完善 + 文档全面更新

**背景**: 修复endplay库双明手分析结果错误问题，完善项目备份系统，更新完整版本历史

**改进**:

1. **双明手分析行列映射修复** (`endplay_integration.py`):
   - 问题：endplay的`calc_dd_table`返回顺序为S,H,D,C,NT，原代码顺序错误导致所有将牌数据错位
   - 修复：修正`trump_order`为`["S", "H", "D", "C", "NT"]`
   - 结果：CLI和Web双明手分析结果正确

2. **备用模型切换功能** (`bridge/bidding_service.py`, `llm/deepseek_client.py`):
   - 主提示词失败时自动切换到备用提示词
   - 备用提示词使用更高温度(0.5)进行自然推理
   - 确保总是返回有效叫品

3. **启动脚本优化** (`start_web.bat`, `start_backend.bat`):
   - 添加`--reload`参数支持热重载
   - 修复uvicorn启动命令格式

4. **叫牌案例记录** (`bidding-cases/case-028.json`):
   - 记录东家4C扣叫错误案例
   - 问题：未确认将牌配合就急于扣叫
   - 正确做法：先叫3S确认将牌配合

5. **本地备份系统完善** (`.trae/skills/create-restore-point/SKILL.md`):
   - 补充遗漏的备份文件：tests/、启动脚本、打包配置等
   - 案例数据加入备份范围
   - 更新skill文档备份清单

6. **Git版本控制更新**:
   - 添加`bidding-cases/`到Git跟踪
   - 推送29个案例文件到远程仓库
   - 创建本地恢复点：`backups/backup_20260326_225200/`

7. **CHANGELOG和DEVELOPMENT文档全面更新**:
   - 补充从v1.0到v1.24的完整版本历史
   - 使用`.trae/skills/update-changelog` skill规范文档格式

**修改文件**:
- `endplay_integration.py`
- `bridge/bidding_service.py`
- `llm/deepseek_client.py`
- `start_web.bat`, `start_backend.bat`
- `bidding-cases/` (29个案例文件)
- `.gitignore`
- `.trae/skills/create-restore-point/SKILL.md`
- `CHANGELOG.md`
- `DEVELOPMENT.md`

**Git提交**:
- `6e15f95`: 修复双明手分析行列映射错误，添加备用模型切换功能，优化启动脚本
- `c03793a`: 添加bidding-cases到Git跟踪，更新create-restore-point skill备份范围
- `2b30812`: 更新CHANGELOG和DEVELOPMENT文档，记录v1.24版本变更

**标签**: `v1.24`

---

## 2026-03-27

### 历史记录共享功能尝试（失败，已回滚）

**背景**: 用户希望CLI端和Web端能够共享历史记录，实现导入导出功能

**尝试的修改**:

1. **后端API** (`api/main.py`):
   - 添加历史记录CRUD接口 (`/api/records`)
   - `RecordCreateRequest` / `RecordResponse` 数据模型
   - 使用 `HistoryManager` 管理记录存储

2. **CLI端** (`main.py`):
   - 添加 `ai_bidding_history` 列表记录每次叫牌详情
   - 修改保存历史记录逻辑，传递详细历史
   - 导入功能支持从JSON文件导入

3. **BiddingService** (`bridge/bidding_service.py`):
   - 添加 `bid_history` 列表
   - 添加 `_record_bid_history()` 方法
   - 在 `ai_bid()` / `_fallback_bid()` / `human_bid()` 中记录

4. **Web端** (`web/src/App.jsx`):
   - 导出功能：将 hands 对象转为字符串，finalContract 转为字符串
   - 导入功能：调用后端API添加记录
   - 加载记录时解析 bid_meaning 和 ai_bidding_history

5. **HistoryManager** (`utils/history.py`):
   - 添加 `ai_bidding_history` 字段到 `BiddingRecord`
   - 修改 `add_record()` 支持新字段

**遇到的问题**:

1. **Web端导入422错误**:
   - 原因：导入时 hands 格式不匹配，某些必需字段缺失默认值
   - 尝试修复：添加 hands 格式转换，为字段提供默认值

2. **CLI端加载记录失败**:
   - 错误：`'dict' object has no attribute 'replace'`
   - 原因：CLI端期望 hands 是字符串格式，但Web端保存的可能是对象格式
   - 位置：`main.py` line 924, `utils/history.py` line 135

3. **数据格式不兼容**:
   - CLI端和Web端的 hands 存储格式不一致
   - CLI端：字符串 `"♠AQ ♥QJ93 ♦853 ♣AQ76"`
   - Web端：对象 `{spades, hearts, diamonds, clubs, hcp, display}`
   - 虽然导出时进行了转换，但导入/加载时仍出现问题

**根本原因**:
- CLI端和Web端的数据模型差异太大
- 需要大量的格式转换逻辑，容易出错
- 两边同时修改导致复杂度倍增

**最终结果**:
- 使用 `git checkout` 回滚所有修改
- CLI端和Web端保持记录隔离状态
- CLI端：文件系统 `bidding_history.json`
- Web端：浏览器 localStorage `biddingRecords`

**经验教训**:
1. 跨平台数据共享需要预先设计统一的数据模型
2. 不应该在两边同时修改，应该先统一后端格式
3. 导入导出功能应该基于统一的后端API，而不是直接操作文件

**回滚的文件**:
- `api/main.py`
- `bridge/bidding_service.py`
- `main.py`
- `utils/history.py`
- `web/src/App.jsx`
- `web/src/services/api.js`

---

## 2026-03-25

### 历史记录导入导出功能（原始需求，未实现）

**背景**: 用户希望实现历史记录的导入导出功能，使终端版和网页版可以共享记录

**原始需求**:
1. **导出功能**: 将历史记录导出为JSON文件，方便备份和分享
2. **导入功能**: 从JSON文件导入历史记录，可以加载其他设备或版本的记录
3. **跨平台共享**: 终端版导出的记录可以在网页版导入，反之亦然

**衍生需求**:
- 统一终端版和网页版的记录格式
- 记录格式需要兼容两种平台的数据结构

**当前状态**:
- 终端版和网页版各自独立管理记录
- 终端版: 文件系统 `bidding_history.json`
- 网页版: 浏览器 localStorage `biddingRecords`
- 两者格式不同，无法互通

**待实现**:
1. 设计统一的记录格式
2. 终端版添加导入/导出菜单选项
3. 网页版添加导入/导出按钮
4. 格式转换逻辑

---

### 统一终端版和网页版记录格式（未完成，已回滚）

**背景**: 尝试统一终端版和网页版的历史记录格式，使两者可以互相加载对方的记录

**目标**:
1. 统一 `aiBiddingHistory` 格式
2. 简化 `finalContract` 格式（移除冗余的搭档信息）
3. 统一 `biddingSequence` 格式（字符串格式）

**修改尝试**:

1. **终端版修改** (`main.py`):
   - 添加 `ai_bidding_history` 初始化和记录逻辑
   - 每次AI叫牌保存详细信息

2. **LLM客户端修改** (`llm/deepseek_client.py`):
   - 返回 `raw_output` 原始LLM输出

3. **网页版修改** (`web/src/App.jsx`):
   - 统一 `aiBiddingHistory` 格式
   - 添加 `biddingSequence` 字符串转数组的转换逻辑
   - 添加 `finalContract` 格式兼容处理

**遇到的问题**:

1. **网页版白屏问题**:
   - 原因：代码中存在使用旧格式 `record.result.bid` 的重复代码
   - 修复：删除重复代码，统一使用新格式 `record.bid`

2. **加载历史记录后不显示手牌和点力**:
   - 原因：历史记录的 `hands` 是字符串格式，但 `HandDisplay` 组件期望对象格式
   - 未解决：需要转换 `hands` 格式或修改保存格式

3. **历史记录文件格式不兼容**:
   - 原因：新格式使用 camelCase（如 `biddingSequence`），旧代码使用 snake_case（如 `bidding_sequence`）
   - 临时解决：删除历史记录文件

**最终结果**:
- 使用 `git restore` 回滚所有修改到上次提交状态
- 删除了不兼容的历史记录文件 `bidding_history.json`
- 终端版和网页版记录管理保持分开

**统一格式设计（供参考）**:
```json
{
  "id": "20260325002338",
  "timestamp": "2026-03-25 00:23:38",
  "hands": { "北": "...", "西": "...", "南": "...", "东": "..." },
  "biddingSequence": "(南)1NT-(西)pass-(北)pass-(东)pass",
  "dealer": "南",
  "gameMode": "双人叫牌",
  "humanPosition": "",
  "aiBiddingHistory": [
    {
      "position": "南",
      "bid": "1NT",
      "meaning": "15-17点，均型或准均型牌...",
      "raw_output": "{完整JSON输出...}"
    }
  ],
  "finalContract": "1NT (南家)",
  "note": "",
  "declarer": "南"
}
```

**待解决问题**:
1. `hands` 格式：字符串 vs 对象
2. 字段命名：camelCase vs snake_case
3. 网页版加载历史记录时的格式转换

**修改文件（已回滚）**:
- `api/main.py`
- `llm/deepseek_client.py`
- `main.py`
- `utils/history.py`
- `web/src/App.jsx`
- `web/src/services/api.js`

---

## 2026-03-24

### 网页版双明手分析显示优化

**背景**: 将双明手分析结果集成到牌桌中央的叫牌过程框内，使用与叫牌过程相同的表格格式显示

**改进**:

1. **双明手结果显示格式**:
   - 创建`DoubleDummyTable.jsx`组件，使用与`BiddingTable`相同的表格格式
   - 顶端显示玩家位置（南西北东），下方显示各花色最高可完成定约
   - 所有单元格统一使用浅蓝色背景
   - 移除HCP显示，只保留定约信息

2. **切换控件优化**:
   - 将Checkbox改为Switch控件，更适合切换场景
   - Switch控件缩小到80%大小
   - 标题动态切换："显示小房子" ↔ "显示叫牌结果"

3. **叫牌细节面板优化**:
   - 下拉框字体大小与标题一致

4. **历史记录加载优化**:
   - 加载历史记录后按钮显示"重新叫牌"
   - 自动切换到显示叫牌过程
   - 清除双明手结果

5. **双明手分析刷新**:
   - 每次切换显示时重新分析，确保结果与当前牌局同步

**修改文件**:
- `api/main.py`: 修改API返回结构化数据
- `web/src/App.jsx`: Switch控件、历史记录加载、字体大小
- `web/src/components/DoubleDummyTable.jsx`: 新增组件
- `web/src/components/CardTable.jsx`: 集成DoubleDummyTable

---

## 2026-03-22

### 双明手分析功能集成（endplay）

**背景**: 集成endplay库实现批量双明手分析，可计算每个玩家在每门花色上坐庄的最高可完成定约

**新增功能**:

1. **endplay集成模块** (`endplay_integration.py`):
   - 手牌格式转换：项目手牌格式 → PBN格式 → endplay Deal对象
   - `analyze_all_contracts_endplay()`: 批量计算所有庄家-将牌组合的最高可完成定约
   - `analyze_specific_contract()`: 分析特定定约能否完成
   - 结果格式化输出：表格形式展示4庄家×5将牌的定约矩阵

2. **主程序集成** (`main.py`):
   - 新增菜单选项"9. 批量双明手分析（endplay）"
   - 支持对当前牌局或输入牌局进行双明手分析
   - 自动检测endplay库是否安装

3. **测试文件**:
   - `test_endplay.py`: endplay库安装和基本功能测试
   - `test_dealer.py`: 发牌模块测试
   - `test_empty_suit.py`: 空花色处理测试
   - `test_random_deal.py`: 随机发牌测试
   - `test_simple.py`: 简单功能测试
   - `test_final.py`: 最终集成测试
   - `test_fix.py`: 修复测试
   - `demo_table.py`: 双明手表演示

4. **Hand类增强** (`bridge/dealer.py`):
   - `to_simple_string()`: 输出简单格式手牌字符串，支持空花色显示为"-"

**依赖**:
- 需要安装endplay库: `pip install endplay`

**修改文件**:
- `endplay_integration.py` (新增)
- `main.py`
- `bridge/dealer.py`
- 多个测试文件 (新增)

---

### 提示词与JF约定优化 - 满贯探查规则整合

**背景**: 备用提示词和JF约定中关于满贯探查的内容有重复，需要优化分工，确保LLM正确完成叫牌

**改进**:

1. **成局定约定义明确** (`llm/prompts.py`):
   - 在基本规则中添加成局定约定义：3NT/4H/4S为25点，5C/5D为28点
   - 强调4C/4D不是成局定约，只是部分定约

2. **关键张计算规则优化** (`llm/prompts.py`):
   - 规则6只保留纯粹的计算逻辑（第一步到第七步）
   - 删除重复的答叫选择规则，改为引用JF约定

3. **4NT问叫/答叫规则简化** (`llm/prompts.py`):
   - 规则7简化为一行引用JF约定
   - 问叫资格检查移至JF约定
   - 禁止pass停在答叫花色规则移至JF约定

4. **扣叫控制规则精简** (`llm/prompts.py`):
   - 只保留防止幻觉规则和输出格式
   - 边花控制检查和问叫资格检查移至JF约定
   - 从约15行精简到约8行

5. **JF约定更新**（用户手动更新docx）:
   - 4.1扣叫控制规则添加步骤4：问叫资格检查
   - 4.3添加禁止pass停在答叫花色规则
   - 4.3添加低花问Q后的答叫规则

**分工明确**:
| 内容 | 位置 |
|------|------|
| 扣叫控制完整流程 | JF约定 4.1 |
| 4NT答叫规则 | JF约定 4.2 |
| 答叫后决策规则 | JF约定 4.3 |
| 防止幻觉 + 输出格式 | 提示词 |
| 关键张计算逻辑 | 提示词 |

**修改文件**:
- `llm/prompts.py`
- `JF实战_标准自然 - Rev 3.2.docx`（用户手动更新）

---

### 成局定约检查规则强化

**背景**: LLM在叫牌时错误地将4D当作成局定约，需要强化规则提醒

**改进**:
- 在"选择最终叫品"步骤添加**【成局定约检查】**规则
- 强调低花成局必须到5阶，4C/4D不是成局定约
- 如果目标是成局且有低花配合，必须选择5C或5D

**修改文件**:
- `llm/prompts.py`

---

### UI优化和进度指示器改进

**背景**: 优化界面布局，修复白屏问题，改进叫牌进度显示

**改进**:

1. **修复白屏问题** (`web/src/components/BiddingControls.jsx`):
   - 恢复`CircularProgress`组件import
   - 解决选择人类玩家位置后白屏的问题

2. **叫牌进度指示器优化** (`web/src/components/CardTable.jsx`):
   - 进度指示器移至手牌框右上角
   - 尺寸缩小（14px），不再显示"思考中..."文字
   - 添加半透明黑色圆形背景
   - 颜色改为黄色（#ffeb3b），在绿色桌面上更醒目
   - 人类叫牌调用LLM时也显示进度

3. **界面设置移除** (`web/src/App.jsx`):
   - 移除"界面设置"部分（配色方案选择）
   - 配色功能代码保留在后台，便于后续添加

4. **手机版布局优化** (`web/src/App.jsx`):
   - 标题"桥牌叫牌练习系统"单独在顶部居中显示
   - 控制按钮在标题下方单独一行
   - 按钮使用较小尺寸（size="small"）
   - 按钮文字简化（"历史"、"API"、"约定"等）

5. **手机版叫品按钮增大** (`web/src/components/BiddingControls.jsx`):
   - 宽度：46px（桌面版44px）
   - 高度：40px（桌面版30px）
   - 字体：0.85rem（桌面版0.8rem）
   - 方便手机端点击操作

**修改文件**:
- `web/src/components/BiddingControls.jsx`
- `web/src/components/CardTable.jsx`
- `web/src/App.jsx`

---

## 2026-03-21

### 桌面版布局优化 + 项目清理

**背景**: 优化桌面版界面布局，清理项目冗余文件

**改进**:

1. **桌面版布局优化** (`web/src/App.jsx`, `web/src/components/BiddingControls.jsx`):
   - 修复重复JF约定片段面板问题
   - 调整牌桌尺寸：宽度700px，高度750px
   - 对齐"当前牌局"和"叫牌细节"面板标题高度
   - 关闭叫牌细节后，叫牌控制和JF约定面板移至右侧，垂直排列
   - 叫品按钮重排：每行10个叫品，紧凑布局
   - 7阶叫品与1、3、5阶对齐，X/XX/Pass与2、4、6阶对齐
   - 添加分割线分隔按钮和面板区域

2. **手机版修复** (`web/src/components/MobileDraggableContainer.jsx`):
   - 删除重复"更多格式"面板

3. **项目清理**:
   - 删除tests目录40个调试临时文件（debug_*.py, check_*.py, find_*.py等）
   - 保留30个正式测试文件（test_*.py）
   - 删除根目录临时文件（package.json, bidding_history.json等）
   - 更新.gitignore：排除screenshots/, Deep Finesse 2014 v2/, .claude/

4. **Git版本控制初始化**:
   - 创建 `.gitignore` 文件，排除敏感文件和构建产物
   - 首次提交：`Initial commit: 桥牌叫牌练习系统 v1.8.2`

5. **GitHub远程仓库配置**:
   - 仓库地址：`https://github.com/fangoner/bridge-bidding-system`
   - API密钥安全：`.env` 已被忽略，不会泄露

6. **项目文档完善**:
   - 添加 `README.md`：项目介绍、安装步骤、使用说明、项目结构
   - 添加 `.env.example`：环境变量配置模板
   - 更新备份skill：结合Git版本控制，包含终端和网页所有文件

**修改文件**:
- `web/src/App.jsx`
- `web/src/components/BiddingControls.jsx`
- `web/src/components/CardTable.jsx`
- `web/src/components/MobileDraggableContainer.jsx`
- `.gitignore`
- `README.md`
- `.env.example`
- `.trae/skills/create-restore-point/skill.md`

**备份位置**: `backups/backup_20260321_023723/`

---

## 2026-03-19

### 恢复到 backup_20260318_pre_refactor

**背景**: 由于叫牌流程合并后出现AI完整输出显示问题，决定恢复到重构前的版本

**操作**:
1. 停止后端服务
2. 恢复 `api/main.py` 到重构前版本
3. 恢复 `bridge/bidding_service.py` 到重构前版本
4. 恢复 `web/src/` 目录下所有文件到重构前版本
5. 删除 `bridge/game_manager.py`

**说明**: 终端和网页叫牌流程合并的工作暂时搁置，待后续重新设计

---

## 2026-03-18

### 网页版叫牌流程重构 + 手机适配 + 设置面板重构

**背景**: 完善网页版叫牌系统，实现手机适配，重构设置面板，统一终端和网页叫牌流程

**改进**:

1. **JF约定片段和预处理逻辑修复** (`bridge/bidding_service.py`):
   - 检索关键词、JF约定片段和预处理结果必须一起传给LLM
   - 两种情况转备用提示词：
     - 预处理结果为空，直接使用备用提示词
     - 预处理结果非空，但主提示词没有选到合格提示词
   - 修复JF约定: 1H-1S但使用了备用提示词的问题

2. **主提示词失败输出显示** (`web/src/App.jsx`, `api/main.py`):
   - 像终端版一样，把主提示词选择合格叫品失败的输出在网页版显示
   - 方便确认是否有转换提示词

3. **网页版手机适配** (`web/src/App.jsx`, `web/src/components/*.jsx`):
   - 使用Material-UI的`sx`属性和`breakpoints`实现响应式设计
   - 牌桌布局在手机上垂直排列
   - JF约定片段框自适应宽度，内容自动换行
   - 叫牌控制面板在手机上100%宽度
   - 桌面版显示保持不变

4. **叫牌控制面板激活逻辑修复** (`web/src/App.jsx`):
   - 修复只有在选择南家为人类玩家时才激活的问题
   - 现在任何位置被设置为人类玩家时都会激活叫牌控制面板

5. **设置面板重构** (`web/src/components/SettingsPanel.jsx`):
   - "游戏设置"改名为"叫牌设置"
   - 新增"发牌设置"组，包含四种发牌模式：
     - 自动发牌（含自由/进局/满贯子模式）
     - 输入自定义牌局
     - 从图片读取牌局
     - 从Edge浏览器截屏
   - 功能实现直接共享终端程序的发牌过程

6. **Deep Finesse格式庄家修复** (`api/main.py`):
   - 问题：网页版总是显示南家为庄家
   - 原因：API端对叫牌序列做重复格式转换导致解析错误
   - 修复：移除重复格式转换，确保庄家位置正确识别

7. **搭档相继pass逻辑修复** (`main.py`, `bridge/game_manager.py`):
   - 问题：第一个实质性叫牌之前的pass也被计入
   - 修复：只在第一个实质性叫牌之后的相继pass才触发自动pass
   - 新增`last_real_bid`属性记录最后一个实质性叫牌

8. **叫牌流程核心逻辑合并到后端API** (`bridge/game_manager.py` - 新建):
   - 创建`BiddingGameManager`单例类管理所有游戏会话
   - 创建`BiddingGame`类封装完整的叫牌游戏逻辑
   - 支持UUID游戏ID，便于多用户并发
   - 终端和网页使用同一个叫牌流程
   - 创建备份确保安全

9. **API端点重构** (`api/main.py`):
   - 新增`/api/game/create` - 创建新游戏
   - 新增`/api/game/{game_id}` - 获取游戏状态
   - 新增`/api/game/{game_id}/deal` - 发牌
   - 新增`/api/game/{game_id}/bid` - 叫牌
   - 新增`/api/game/{game_id}/formats` - 获取输出格式

10. **AI叫牌失败422错误修复** (`api/main.py`):
    - 问题：AI叫牌时返回422错误
    - 原因：`GameBidRequest`的bid字段是必填的
    - 修复：修改`GameBidRequest`使bid字段可选

11. **发牌逻辑说明**:
    - 自由发牌：随机发牌，70%概率将最强牌放在南北
    - 进局实力：南北HCP>=25时接受，最多尝试1000次
    - 满贯实力：南北HCP>=28时接受，最多尝试1000次

**修改文件**:
- `bridge/game_manager.py` (新建)
- `bridge/bidding_service.py`
- `api/main.py`
- `main.py`
- `web/src/App.jsx`
- `web/src/components/AIOutputPanel.jsx`
- `web/src/components/SettingsPanel.jsx`
- `web/src/components/BiddingControls.jsx`

**备份位置**: `backups/backup_20260318/`

---

## 2026-03-15

### 检验定约功能 + 术语修正 + Deep Finesse格式优化 + UI改进

**背景**: 添加检验定约功能，修正桥牌术语，优化Deep Finesse格式显示，改进用户界面

**改进**:

1. **添加检验定约功能** (`api/main.py`, `web/src/App.jsx`, `bridge/deep_finesse.py`):
   - 新增`/api/analyze-contract`接口，调用Deep Finesse分析定约
   - 前端新增"检验定约"按钮（在更多格式框标题栏）
   - 点击后自动启动Deep Finesse并置顶窗口
   - 使用`EnumWindows`和`GetWindowThreadProcessId`查找窗口并置顶

2. **术语修正** (`web/src/App.jsx`, `llm/prompts.py`):
   - 将"庄家"改为"发牌人"（第一个叫牌的人）
   - 保留"庄家"用于最终定约显示（定约方中第一个叫出该花色的人）
   - 修改提示词中"第一家（庄家）"为"第一家（发牌人）"

3. **Deep Finesse格式优化** (`bridge/output_format.py`):
   - 第一行：Deal: 1 后22个空格
   - 第二行：东西手牌之间4个空格
   - 第三行：West 后17个空格
   - 确保在500px宽度内正常显示

4. **UI改进** (`web/src/App.jsx`):
   - "发牌"按钮改为"重新发牌"（已有牌局时）
   - 更多格式框宽度改为500px
   - 叫牌结束时自动隐藏JF约定片段框
   - 加载历史记录时避免重复保存（使用`useRef`）

5. **终端程序自动pass叫牌含义** (`main.py`):
   - 自动pass时添加叫牌含义："搭档已相继pass，不再参与叫牌"

**修改文件**: `api/main.py`, `web/src/App.jsx`, `bridge/deep_finesse.py`, `bridge/output_format.py`, `llm/prompts.py`, `main.py`

**测试验证**: 检验定约功能正常工作；Deep Finesse窗口自动置顶；术语显示正确

---

## 2026-03-14

1. **修复更多格式框不显示问题** (`api/main.py`):
   - 问题根源：API中重复定义了Position枚举类，与bridge.dealer导入的Position冲突
   - 错误现象：API返回500错误，detail为`<Position.NORTH: '北'>`
   - 解决方案：删除API中重复定义的Position枚举类，使用bridge.dealer导入的枚举

2. **加载历史牌局后显示更多格式** (`web/src/App.jsx`):
   - 新增`fetchOutputFormatsForRecord`函数，在加载历史记录后获取输出格式
   - 修改`loadRecordToTable`函数，调用格式生成API
   - 方便用户检验历史叫牌结果

3. **更多格式框宽度调整** (`web/src/App.jsx`):
   - 将宽度固定为430px

4. **终端程序添加搭档相继pass后自动pass功能** (`main.py`):
   - 新增`passed_partnership`属性记录已相继pass的搭档
   - 新增`check_partner_consecutive_pass`函数检测搭档是否相继pass
   - 新增`is_in_passed_partnership`函数检查位置是否属于已pass的搭档
   - 修改`run_bidding_loop`实现自动pass逻辑
   - 检测逻辑：搭档pass -> 对方叫牌或pass -> 当前pass = 相继pass

**修改文件**: `api/main.py`, `web/src/App.jsx`, `main.py`

**测试验证**: API返回200状态码，紧凑格式和Deep Finesse格式正确显示；终端程序自动pass功能测试通过

---

## 2026-03-14

### Web版叫牌历史累积和AI调用优化

**背景**: 修复网页版叫牌历史丢失问题，并优化四人叫牌模式下的AI调用效率

**改进**:

1. **叫牌历史累积功能修复** (`web/src/App.jsx`, `llm/prompts.py`):
   - 网页版叫牌历史格式与终端版保持一致：`\n(位置)叫品含义`
   - 每次叫牌后累积叫品含义，形成完整的叫牌历史
   - 修改提示词中"叫牌历史"字段描述，直接引用累积内容

2. **叫牌结束后添加"重新叫牌"按钮** (`web/src/App.jsx`):
   - 叫牌结束界面新增"重新叫牌"按钮
   - 保持当前牌局，重新开始叫牌流程
   - 新增 `resetBidding()` 函数处理重置逻辑

3. **四人叫牌模式AI调用优化** (`web/src/App.jsx`):
   - 添加 `passedPartnership` 状态记录已相继pass的搭档（'南北' 或 '东西'）
   - 搭档两人相继pass后（中间只有对方的一次叫牌或pass），后续直接pass（不调用AI）
   - 例如：`西家pass -> 北家叫牌 -> 东家pass`，此时东西搭档已相继pass
   - pass仍加入叫牌序列和叫牌历史，避免分析错误
   - 另一方两人正常调用AI叫牌
   - 人类玩家属于已pass搭档时，自动pass并显示提示信息
   - 新增 `isInPassedPartnership()` 辅助函数判断位置是否属于已pass的搭档

4. **Vite配置固定端口** (`web/vite.config.js`):
   - 添加 `strictPort: true` 配置
   - 固定前端端口为5173，不再自动切换

**修改文件**: `web/src/App.jsx`, `llm/prompts.py`, `web/vite.config.js`

**测试验证**: 叫牌历史正确累积，四人模式AI调用优化生效

---

## 2026-03-14

### Web版JF约定片段显示和叫牌逻辑优化

**背景**: 完善Web版桥牌叫牌练习系统的JF约定片段显示功能和叫牌流程控制

**改进**:

1. **JF约定片段显示优化** (`web/src/App.jsx`):
   - 用户点击"显示JF约定片段"checkbox时，根据当前叫牌序列获取JF约定片段
   - 没有相关约定时显示"JF尚未提供建议"
   - 取消勾选时清空显示内容
   - checkbox的onChange事件立即触发获取JF约定片段

2. **JF约定片段框布局调整** (`web/src/App.jsx`):
   - 水平方向和LLM输出框右端对齐
   - 固定最大高度300px，与叫牌控制框高度一致
   - 内容区域使用overflow: auto实现滚动条
   - 标题使用flexShrink: 0防止被压缩
   - 叫牌控制框宽度固定为320px

3. **叫牌逻辑优化** (`web/src/App.jsx`):
   - 发牌后biddingStarted设置为false，需要等待开始
   - 观察模式：需要点击"开始叫牌"按钮，AI全程自动叫牌
   - 人类参与但不是第一个叫牌：需要点击"开始叫牌"按钮
   - 人类第一个叫牌：发牌后等待人类叫牌，人类叫牌后AI继续
   - 人类叫牌后，biddingStarted自动设置为true，AI会继续叫牌直到轮到人类
   - 修改useEffect逻辑，区分观察模式和人类参与模式

**修改文件**: `web/src/App.jsx`

**测试验证**: 所有叫牌场景正常工作

---

## 2026-03-13

### Web版桥牌叫牌练习系统全面完善

**背景**: 完善Web版桥牌叫牌练习系统，实现完整的AI叫牌流程和用户交互

**改进**:

1. **叫牌按钮和AI叫牌流程** (`web/src/App.jsx`, `api/main.py`, `web/src/services/api.js`):
   - 添加"开始叫牌"按钮，发牌后需点击按钮启动叫牌
   - AI叫牌过程匹配终端版本：关键字提取、JF约定片段检索、预处理、主提示词、备用提示词
   - 修复观察模式AI无法自动叫牌的问题（修改useEffect条件）
   - 添加checkbox控制是否显示完整AI叫牌输出

2. **LLM输出框优化** (`web/src/App.jsx`, `web/src/App.css`):
   - 响应式设计：电脑屏幕在牌桌右侧大框显示，手机屏幕在牌桌下方显示
   - 添加进度条显示叫牌正在进行
   - LLM输出框高度与牌桌高度一致，内容可滚动
   - 下拉框选择查看不同位置的叫牌历史记录
   - 添加checkbox切换简单显示模式（只显示位置、叫品、叫牌含义）

3. **API和网络优化** (`api/main.py`, `web/src/services/api.js`, `web/vite.config.js`):
   - 修复CORS问题，更新后端允许的前端端口
   - 增加API超时时间从30秒到120秒
   - 启用LAN访问，其他机器可通过局域网IP访问
   - 优化LLM客户端初始化，从每次请求创建改为全局客户端

4. **庄家显示修复** (`web/src/App.jsx`):
   - 修复庄家识别逻辑：显示第一个叫该花色的人，而不是最后一个
   - 符合桥牌规则：庄家是第一个叫成定约花色的人

5. **叫牌记录管理** (`web/src/App.jsx`):
   - 自动记录每次叫牌完整结果，包括LLM完整输出
   - 使用localStorage持久化存储
   - 支持查看、编辑、删除历史记录
   - Dialog组件实现记录管理界面

6. **JF约定片段功能** (`web/src/App.jsx`):
   - "获取建议"功能改为显示JF约定片段，而不是实际调用AI叫牌
   - JF约定片段框位于叫牌控制框右侧
   - 只在人类叫牌时显示，AI叫牌时不显示
   - 添加checkbox控制是否显示JF约定片段

7. **双人叫牌流程修复** (`web/src/App.jsx`):
   - 修复双人叫牌时对方阵营自动pass的显示问题
   - 叫牌结果正确显示在叫牌表格中
   - 不参与叫牌位置的默认pass也会显示

**修改文件**:
- `web/src/App.jsx`: 主要组件逻辑
- `web/src/App.css`: 样式文件
- `web/src/services/api.js`: API服务层
- `web/vite.config.js`: Vite配置
- `api/main.py`: 后端API

**测试验证**: 所有功能正常工作

---

## 2026-03-12

### Web版桥牌叫牌练习系统功能完善

**功能**: 完善Web版桥牌叫牌练习系统的游戏设置和牌桌显示功能

**实现**:
1. **游戏设置面板** (`web/src/App.jsx`):
   - 叫牌模式选择：四人叫牌 / 双人叫牌
   - 庄家位置设置：南家、西家、北家、东家
   - 人类玩家位置：观察模式 / 南家 / 西家 / 北家 / 东家
   - 显示队友手牌复选框（双人模式）
   - 显示AI手牌复选框（四人模式）
   - 显示对方手牌复选框（双人模式）

2. **牌桌布局优化** (`web/src/App.jsx`, `web/src/App.css`):
   - 经典桥牌桌布局：北家在上，南家在下，东西家在中间两侧
   - 牌桌中心显示叫牌过程和叫牌表格
   - 隐藏手牌时显示占位符，保持布局稳定
   - 当前叫牌者高亮显示（金色边框）
   - 庄家位置标识（*号）
   - 人类玩家标识（[你]）
   - 队友标识（[队友]）

3. **手牌显示逻辑**:
   - 观察模式：显示所有手牌
   - 四人模式 + 人类玩家：只显示自己的牌，AI牌默认隐藏
   - 双人模式 + 人类玩家：显示自己的牌，队友和对方牌根据设置显示
   - 隐藏的手牌显示"[隐藏]"占位符

4. **叫牌控制面板**:
   - 显示当前叫牌者
   - 人类玩家回合时启用叫牌按钮
   - AI回合时显示"等待AI叫牌..."
   - 支持所有叫品：1C-7NT、X、XX、pass

**默认设置**:
- 显示队友手牌：false（默认隐藏）
- 显示AI手牌：false（默认隐藏）
- 显示对方手牌：false（默认隐藏）

**文件位置**:
- `web/src/App.jsx`: 主要组件逻辑
- `web/src/App.css`: 样式文件
- `web/src/services/api.js`: API接口

---

## 2026-03-11

### 1高花开叫后对方干扰的关键字提取优化

**背景**: 原逻辑中，1H/1S开叫后对方干扰的情况统一使用"我方开叫1高花"关键字，无法精确匹配JF约定中的细分章节。

**改进**:
- len(bids)==2场景：区分对方加倍、双套争叫、普通争叫
- len(bids)==4场景：区分再加倍、简单加叫后敌方参与

**关键字映射表**:

| 场景 | 序列示例 | 关键字 |
|------|----------|--------|
| len==2, 对方加倍 | `1H-(X)-?` | `12.2.1 敌方加倍` |
| len==2, 确定双套争叫 | `1H-(2NT)-?` | `对抗对方已明确的 55 双套争叫：` |
| len==2, 已知一套双套争叫 | `1H-(2H)-?` | `对抗对方只已知一套的 55 双套争叫：` |
| len==2, 普通争叫 | `1H-(1S)-?` | `12.2.2 敌方争叫花色` |
| len==4, 再加倍 | `1H-(X)-XX-?` | `12.2.4 关于再加倍` |
| len==4, 简单加叫后敌方参与 | `1H-(P)-2H-(争叫)` | `12.2.3 我方简单加叫后敌方参与` |

**修改文件**: `bridge/bidding.py`

**测试验证**: 所有测试场景关键字提取通过

---

### 1低花开叫后双套争叫关键字提取优化

**背景**: 1C/1D开叫后对方双套争叫的情况需要单独处理。

**改进**:
- 1C-2C：对方双高花55双套争叫
- 1C-2NT：对方5H+5D双套争叫
- 1D-2D：对方双高花55双套争叫
- 1D-2NT：对方5H+5C双套争叫

**关键字映射表**:

| 场景 | 序列示例 | 关键字 |
|------|----------|--------|
| 1C双套争叫 | `1C-(2C)-?` | `对抗对方已明确的 55 双套争叫：` |
| 1C双套争叫 | `1C-(2NT)-?` | `对抗对方已明确的 55 双套争叫：` |
| 1D双套争叫 | `1D-(2D)-?` | `对抗对方已明确的 55 双套争叫：` |
| 1D双套争叫 | `1D-(2NT)-?` | `对抗对方已明确的 55 双套争叫：` |

**修改文件**: `bridge/bidding.py`

**测试验证**: 所有测试场景关键字提取通过

---

### 跳扣叫关键字提取

**背景**: 敌方1阶开叫后，我方3阶跳扣叫同一花色表示问挡张，需要单独处理。

**改进**:
- 序列 `(1X)-3X-(pass/争叫)-?` 返回关键字"跳扣叫"
- 例如：`(1C)-3C-pass`、`(1H)-3H-3S` 等

**修改文件**: `bridge/bidding.py`

**测试验证**: 所有测试场景关键字提取通过

---

## 2026-03-10

### 1C/1D开叫后对方干扰的关键字提取优化

**背景**: 原逻辑中，1C/1D开叫后对方干扰的情况统一使用"我方开叫1低花"关键字，无法精确匹配JF约定中的细分章节。

**讨论过程**:
1. 分析JF约定文档中"我方开叫1低花"章节的结构
2. 识别出以下细分场景需要单独提取：
   - 对方加倍后（12.1.1）
   - 对方一阶争叫
   - 对方二阶争叫
   - 低花反加叫被干扰
   - 开叫人的再叫
3. 确认各场景的关键字格式（注意"对方二阶争叫："需要冒号）
4. 理清"开叫人的再叫"的准确条件：第二家或第四家至少有一家争叫，排除低花反加叫被干扰的情况

**关键问题**:
- 问题1：初始方案中"低花反加叫被干扰"条件不完整
  - 错误：只检查`third_bid=="2C"`和`fourth_bid!=pass`
  - 修正：必须同时检查`first_bid=="1C"`（或1D），确保`second_bid=="pass"`
  - 正确序列：`1C-(P)-2C-(争叫)` 和 `1D-(P)-2D-(争叫)`

- 问题2：初始方案中"开叫人的再叫"条件错误
  - 错误：`second_bid != "pass"`
  - 修正：`second_bid != "pass" or fourth_bid != "pass"`（第二家或第四家至少有一家争叫）

- 问题3：`len(bids)==4`时`third_bid=="pass"`的情况被遗漏
  - 原因：条件`third_bid != "pass"`阻止了队友pass的情况
  - 修正：将1C/1D的处理逻辑提前，优先判断

**关键字映射表**:

| 场景 | 序列示例 | 关键字 |
|------|----------|--------|
| len(bids)==2, 对方加倍 | `1C-(X)-?` | `12.1.1 对方加倍后` |
| len(bids)==2, 对方一阶争叫 | `1C-(1H)-?` | `对方一阶争叫` |
| len(bids)==2, 对方二阶争叫 | `1C-(2H)-?` | `对方二阶争叫：` |
| len(bids)==2, 对方高阶争叫 | `1C-(3H)-?` | `我方开叫1低花` |
| len(bids)==4, 低花反加叫被干扰 | `1C-(P)-2C-(争叫)` | `低花反加叫被干扰` |
| len(bids)==4, 低花反加叫被干扰 | `1D-(P)-2D-(争叫)` | `低花反加叫被干扰` |
| len(bids)==4, 开叫人的再叫 | `1C-(1H)-*-*` | `开叫人的再叫` |
| len(bids)==4, 开叫人的再叫 | `1C-(P)-1H-(争叫)` | `开叫人的再叫` |

**修改文件**: `bridge/bidding.py`

**测试验证**: 所有18个测试场景关键字提取通过

**备份位置**: `backups/backup_20260310_000412/`

---

## 2026-03-08

### 1NT开叫后对方争叫的关键字提取优化

- 根据`deal_system`配置区分对方争叫类型
- 细化关键字提取逻辑，精确匹配JF约定章节
- 新增应叫被干扰场景的关键字提取
- 支持两种二阶开叫方案的关键字区分

**关键字映射表**:

| 对方叫品 | deal_system | 关键字 | 章节 |
|---------|-------------|--------|------|
| X | 自然阻击 | `12.3` | 12.3.1 加倍示强 |
| X | 多功能/麦德伯格 | `12.3.2\t 对方加倍表示别的含义` | 12.3.2 |
| 2C | 任意 | `12.3.5\t 对方非自然争叫` | 12.3.5 双高花 |
| 2NT | 任意 | `12.3.5\t 对方非自然争叫` | 12.3.5 双低花 |
| 2D/2H/2S | 自然阻击 | `12.3.4\t Rubensohl 约定叫` | 12.3.4 |
| 2D/2H/2S | 多功能/麦德伯格 | `12.3.5\t 对方非自然争叫` | 12.3.5 |
| ≥3阶 | 任意 | `12.3.6\t 对方高阶争叫` | 12.3.6 |
| 应叫被干扰 | 任意 | `12.3.3\t Stayman/转移叫被干扰` | 12.3.3 |

**设计逻辑**:
- 二阶开叫方案选择"自然阻击"时，对方争叫也倾向于自然含义
- 二阶开叫方案选择"多功能/麦德伯格"时，对方争叫倾向于非自然含义
- 应叫被干扰：我方开叫1NT后，应叫被对方X或争叫干扰

**修改文件**: `bridge/bidding.py`

**测试验证**: 所有场景关键字提取和检索测试通过

---

### 结构性约定判断逻辑简化

**背景**: 原逻辑中存在两个功能重叠的参数 `has_structure` 和 `is_structural_convention`，增加了代码复杂度。

**改进**:
1. **简化 `is_structural_convention` 函数** (`knowledge/loader.py`):
   - 移除基于内容缩进的判断逻辑
   - 只保留三种结构性约定类型：
     - 开叫关键字（如 `1H开叫`、`1NT`、`2C`）
     - 双叫品关键字（如 `1D-1H`、`1C-1D`）
     - 第三四家开叫1高花（如 `第三四家开叫1H`）
   - 其他情况（包括 `12.3.x` 章节号关键字）均返回 False

2. **移除 `has_structure` 参数**:
   - 从 `preprocess_jf_content` 返回结果中移除
   - 用 `len(subsequent_bids) > 0` 替代原判断逻辑
   - 更新 `main.py` 中所有引用位置

**修改文件**: `knowledge/loader.py`, `main.py`

**效果**: 
- `12.3.x` 系列约定片段现在被识别为非结构性约定
- 程序直接走备用提示词，使用当前JF片段
- 不再转向"成局与满贯"关键字

---

## 2026-03-06

### 打包发布功能实现

**功能**: 实现完整的打包发布流程，支持将程序打包为独立EXE和安装程序

**实现**:
1. **PyInstaller打包配置** (`build.spec`):
   - 配置打包参数，包含JF约定文档和配置模板
   - 生成单文件EXE（约30-50MB）

2. **打包脚本**:
   - `build.bat`: 快速打包脚本
   - `update_release.ps1`: 一键更新发布包脚本
   - `update_release.bat`: 批处理入口

3. **安装程序配置** (`installer.iss`):
   - Inno Setup安装脚本
   - 支持中文界面
   - 自动配置API密钥模板

4. **发布文档**:
   - `README.txt`: 用户使用手册
   - `LICENSE.txt`: 许可协议
   - `.env.example`: API配置模板

**发布包结构**:
```
release_桥牌叫牌练习/
├── 桥牌叫牌练习.exe           # 主程序
├── JF实战_标准自然 - Rev 3.2.docx  # 约定文档
├── .env.example              # API配置模板
├── README.txt                # 使用说明
├── LICENSE.txt               # 许可协议
└── Deep Finesse 2014 v2/     # 分析工具
```

**使用方法**:
- 用户复制 `.env.example` 为 `.env`
- 填入DeepSeek API密钥
- 双击运行 `桥牌叫牌练习.exe`

---

### 历史记录管理界面优化

**问题**: 执行命令后，操作结果显示在菜单后面，需要翻页查看

**修复** (`main.py`):
- 重构 `view_history` 函数显示顺序
- 操作结果现在显示在记录清单后面、菜单前面
- 使用 `result_message` 列表存储操作结果，每次循环开始时显示并清空

**显示流程**:
```
1. 显示记录清单
2. 显示操作结果（如果有）
3. 显示操作选项菜单
```

---

### LLM幻觉问题修复

**问题**: LLM在判断边花控制时，编造手牌中没有的牌张（如手牌♦84却判断为有♦K控制）

**修复** (`llm/prompts.py`):
- 在"扣叫控制"部分增加防幻觉规则
- 要求必须先列出该花色的所有牌张，再判断控制级别
- 明确禁止编造牌张
- 要求每次判断必须引用实际持牌作为依据

**输出格式要求**:
```
- '♣：手牌有♣AKQ8，有 A 和 K → 第一轮和第二轮控制'
- '♦：手牌有♦84，无 A/K/单缺 → 无控制'
```

---

## 2026-03-01

### 叫品提取和检索逻辑修复

**问题1**: 预处理结果中缺少3NT叫品
- **原因**: `extract_response_bids`函数只检查中文冒号"："，而JF约定文档中3NT使用英文冒号":"
- **修复** (`knowledge/loader.py`): 修改函数同时检查中文冒号和英文冒号
- **结果**: 预处理结果从26个增加到28个，现在包含3NT叫品

**问题2**: 模糊匹配导致错误返回约定片段
- **原因**: `retrieve`函数在找不到精确匹配时，会进行模糊匹配（`query in keyword or keyword in query`），导致"1NT-3NT"错误匹配到"1NT开叫"
- **修复** (`knowledge/loader.py`): 移除所有模糊匹配逻辑，只保留精确匹配
- **结果**: 当找不到精确匹配的关键词时，返回空内容，主提示词输出"JF无合格叫品"后转向备用提示词

**问题3**: 主提示词未完成所有叫品验证
- **原因**: 最初怀疑是LLM输出长度限制，但实际原因是预处理结果中缺少正确的叫品（3NT）
- **修复**: 通过修复问题1和问题2，确保预处理结果包含所有叫品

**代码位置**:
- `knowledge/loader.py`: `extract_response_bids`函数、`retrieve`函数

**测试结果**:
- 1NT开叫预处理结果：28个叫品（包含3NT）✓
- 1NT-3NT检索：返回空内容（正确行为）✓

---

## 2026-02-26

### 树结构转换和多叫品拆解功能实现

**功能**: 实现桥牌约定片段的树结构转换和多叫品拆解功能
**目的**: 支持双叫品关键词和第三四家开叫1高花的树结构导航，以及多叫品拆解

**实现** (`knowledge/loader.py`):

1. **树结构转换功能** (`parse_content_to_tree`):
   - 支持双叫品关键词（如1D-1H、1C-1D、2D-2NT）
   - 支持第三四家开叫1高花（如第三四家开叫1H、第三四家开叫1S）
   - 自动识别根节点并构建嵌套树结构
   - 双叫品关键词：根节点为第一个叫品，子节点为第二个叫品
   - 第三四家开叫：根节点为开叫品（1H或1S）

2. **多叫品拆解功能**:
   - 识别包含"/"的叫品行（如"2S/3C/D/H"、"3C/D/H/S"、"3S/4C"）
   - 自动拆解成多个并列叫品
   - 单个字母叫品（C、D、H、S）自动推断为3阶叫品
   - 所有拆解的叫品共享相同的描述

3. **树结构导航功能** (`navigate_tree_by_bids`):
   - 根据叫牌序列在树结构中导航到目标节点
   - 自动处理根节点（跳过开叫品）
   - 支持双叫品关键词和第三四家开叫的导航

4. **预处理逻辑更新** (`preprocess_jf_content`):
   - 双叫品关键词：使用树结构导航提取队友叫品和后续叫品
   - 第三四家开叫：使用树结构导航提取队友叫品和后续叫品
   - 自动设置正确的start_idx（跳过开叫品）

**测试结果**:
- 1D-1H：所有测试序列正常工作 ✓
- 1C-1D：所有测试序列正常工作 ✓
- 2D-2NT：所有测试序列正常工作 ✓
- 第三四家开叫1H：所有测试序列正常工作 ✓
- 第三四家开叫1S：所有测试序列正常工作 ✓
- 多叫品拆解："2S/3C/D/H"→"2S"、"3C"、"3D"、"3H" ✓
- 多叫品拆解："3C/D/H/S"→"3C"、"3D"、"3H"、"3S" ✓
- 多叫品拆解："3S/4C"→"3S"、"4C" ✓

**代码位置**:
- `knowledge/loader.py`: 树结构转换、导航、预处理逻辑
- `main.py`: 与预处理程序的接口调用

---

### 牌型表示规则优化

**问题**: AI误解"5+"和"没有4张或以上高花"的含义
- 案例1：1D-2C后，AI判断"5+D满足"，但手牌只有4张D
- 案例2：AI判断"无4+高花满足"，但手牌有4张H

**修复** (`llm/prompts.py`):
- 在主提示词和备用提示词的"牌型表示"部分增加两条说明：
  1. **"x+"或"x张以上"的严格含义**：表示"至少x张"，少一张都不合格。例如"5+"表示至少5张，4张不合格；"4张以上"表示至少4张，3张不合格。
  2. **"没有x张或以上花色"的含义**：表示所有该类花色都少于x张。例如"没有4张或以上高花"表示S和H都少于4张（即S≤3张且H≤3张），如果S或H有4张或更多则不合格。

### 序列匹配和牌型严格检查规则优化

**问题**: AI在1S-2C后错误地使用了1S-2C-2S序列下的2NT描述（5S332），并用"接近"模糊匹配牌型
- AI判断"牌型为5-2-4-2，接近5-3-3-2，JF约定未明确禁止非严格5332，视为允许"

**修复** (`llm/prompts.py`):
- 在主提示词和备用提示词的叫品筛选过程中增加两条检查规则：
  1. **序列匹配严格检查（绝对禁止混用）**：必须精确匹配叫牌序列，禁止跨序列混用
  2. **牌型严格检查（绝对禁止模糊匹配）**：牌型必须严格匹配，禁止使用"接近"、"类似"等模糊表述

### 点力范围严格检查规则优化

**问题**: AI在1S-1NT判断中使用"通常6+点"模糊表述突破5-12点范围限制

**修复** (`llm/prompts.py`):
- 在主提示词和备用提示词的叫品筛选过程中增加点力范围严格检查规则：
  - 点力范围是绝对门槛，禁止使用模糊表述突破限制
  - 示例：JF约定写"5-12点"，手牌14点 → 绝对不合格

### 备用提示词默认AI模型调整

**修改** (`config.py`):
- 将 `DEFAULT_FALLBACK_MODEL` 从 `FALLBACK_MODEL_REASONER` 改为 `FALLBACK_MODEL_CHAT`

---

## 2026-02-23

### 扣叫控制规则优化

**问题1**: AI跳过有控制的花色直接扣叫更高花色
**修复** (`llm/prompts.py`):
- 新增扣叫顺序规则：必须按♣→♦→♥→♠顺序检查，有控制就扣叫，无控制就跳过
- 明确示例：有♦K和♥A控制，必须依次叫4♦然后4♥，不能跳过4♦直接叫4♥

**问题2**: AI认为需要同时有AK才算有控制
**修复** (`llm/prompts.py`):
- 明确控制定义：有A、或有K、或单张、或缺门，即算有控制（不需要同时有AK）
- 明确边花控制：3门边花都有控制即视为控制齐全，应直接4NT
- 添加示例：将牌为♠，队友显示♥有控制，自己有♦A和♣A，则3门边花都有控制，应直接4NT

**问题3**: AI以"止叫"为由违反叫品递增规则
**修复** (`llm/prompts.py`):
- 强调叫品递增是绝对规则，禁止例外
- 新增止叫规则：想停在成局定约时，必须叫高于当前叫品的将牌花色
- 明确示例：当前5C，想止叫必须叫5S（不能叫4S，因为4S<5C）

### 4NT问叫/答叫后重点规则优化

**问题**: 4NT问叫后的决策逻辑不完整，缺少4关键张+无Q的情况处理
**修复** (`llm/prompts.py`):
- 阶段三细分为4种情况：
  1. 4关键张+Q已确认 → 小满贯
  2. 4关键张+无Q → 停在成局
  3. 5关键张+Q已确认 → 可以问K或小满贯
  4. 5关键张+无Q → 小满贯
- 明确问将牌Q后的答叫处理：根据答叫结果（有Q或无Q）进入阶段三相应分支

---

## 2026-02-22

### 恢复点 v1.8.1

**状态**: 预处理逻辑已完成，备用提示词待优化

**已完成**:
- 预处理逻辑重写，支持四种结构性约定片段
- 移除后续建议功能
- 备用提示词逻辑优化（不使用预处理结果）
- 提示词阶段合并，减少token消耗
- bid_meaning传递机制修复

**待解决**:
- 备用提示词中AI混淆自己和队友的叫品
- 示例：北家开叫1H，南家应叫2C后，北家再叫时AI错误地将1H当作队友的叫品

**代码位置**:
- `knowledge/loader.py`: 预处理逻辑
- `llm/prompts.py`: 主提示词、备用提示词
- `main.py`: 叫牌流程控制

---

### 预处理逻辑重写

**问题**: 预处理逻辑无法正确处理四种结构性约定片段
**修复** (`knowledge/loader.py`):

重写 `preprocess_jf_content` 函数，根据四种结构性约定片段类型分别处理：

| 类型 | 关键字示例 | 处理方式 |
|------|-----------|----------|
| 1. 花色开叫 | "花色开叫"、"1C开叫" | 无序列时提取开叫叫品；有序列时提取应叫叫品 |
| 2. 开叫后第一应叫 | "1C开叫" | 提取应叫叫品列表 |
| 3. 开叫-应叫后续 | "1C-1D"、"1H-1S" | 在树中定位队友叫品，提取直接后续 |
| 4. 第三四家1高花 | "第三四家开叫1H" | 序列≤1时提取应叫叫品；序列>1时定位队友叫品提取后续 |

新增辅助函数：
- `extract_bids_from_sequence`: 从叫牌序列提取叫品列表
- `extract_first_level_bids`: 提取第一层所有叫品
- `extract_first_level_bids_excluding_opening`: 提取第一层叫品（排除开叫叫品）
- `extract_response_bids`: 提取应叫叫品列表
- `find_partner_bid_in_tree`: 在树状结构中定位队友叫品

修复 `extract_subsequent_bids` 函数：
- 区分关键字行（如`1NT-2C`）和树节点行（如`├3S`）
- 关键字行：后续叫品是缩进0的分支
- 树节点行：后续叫品是缩进+1的子节点

测试结果：
- `(南)pass-(西)pass-(北)1NT-(东)pass-(南)2C-(西)pass-` → 2D、2H、2S ✓
- `(南)pass-(西)pass-(北)1NT-(东)pass-(南)2C-(西)pass-(北)2D-(东)pass-(南)2S-(西)pass-` → 2NT、3S ✓
- `(南)1H-(西)pass-(北)3D-(东)pass-(南)3S-(西)pass-` → 3NT、4C、4D、4H ✓

### 移除后续建议功能

**问题**: 后续建议功能增加了系统复杂度，但实际效果有限
**修复** (`knowledge/loader.py`, `main.py`, `llm/prompts.py`):
- 删除 `extract_nested_subsequent_bids` 函数
- 简化 `extract_subsequent_bids`、`extract_opening_bids`、`extract_response_bids_from_opening` 函数，不再提取二级叫品
- 简化 `_format_subsequent_bids` 方法，只输出一级叫品
- 更新所有提示词模板（主提示词、备用提示词、人类提示词）：
  - 删除"后续建议"和"队友建议"相关字段
  - 删除"叫品含义及后续建议"字段，改为"叫品含义"
  - 简化叫品筛选过程逻辑

### 备用提示词逻辑优化

**问题**: 备用提示词不应该使用预处理结果，因为主提示词已验证预处理结果无合格叫品
**修复** (`main.py`, `llm/prompts.py`):
- 从主提示词切换到备用提示词时，`subsequent_bids` 设为空字符串
- 备用提示词叫品筛选过程：从JF约定原文提取 → 自然约定
- 删除预处理结果优先级

### 人类提示词逻辑优化

**问题**: 人类提示词需要根据约定类型决定JF约定内容
**修复** (`main.py`):
- 结构性约定 + 有预处理结果：`jf_content=""`, `subsequent_bids`=预处理结果
- 描述性约定或无预处理结果：`jf_content`=完整JF约定片段, `subsequent_bids=""`

### 结构性约定预处理为空时切换到"成局与满贯"

**问题**: 序列 `1C-1S-1NT-2C-2D-2S` 后，预处理结果为空，但备用提示词仍使用原关键词"1C-1S"
**修复** (`main.py`):
- 修改 `ai_bid()` 中的判断逻辑：
  - 描述性约定 → 备用提示词 + 完整JF约定片段
  - 结构性约定 + 预处理为空 → 备用提示词 + "成局与满贯"约定
  - 结构性约定 + 预处理非空 → 主提示词 → (无合格叫品) → 备用提示词 + "成局与满贯"约定
- 新增 `jf_keyword` 参数传递，确保备用提示词显示正确的关键词

### 叫品递增规则加强说明

**问题**: LLM误认为 2D 低于 2C（实际 D > C）
**修复** (`llm/prompts.py`):
- 主提示词和备用提示词都加强叫品递增规则说明：
  - 明确花色等级：**S > H > D > C**（黑桃 > 红心 > 方块 > 草花）
  - 增加具体例子：`2D > 2C`（同阶，D > C）、`2H > 2D`（同阶，H > D）、`1NT > 1S`（阶次更高）

## 2026-02-21

### 叫品提取统一转大写

**问题**: 叫品提取时没有统一转大写，导致 'x' 和 'X' 比较失败，无法正确识别技术性加倍
**修复** (`bridge/bidding.py`):
- 提取叫品后统一转为大写
- 'P' 和 'PASS' 转为 'pass'
- 测试结果：
  - `(南)pass-(西)pass-(北)1C-(东)x-` → "我方开叫1低花" ✓
  - `(南)pass-(西)pass-(北)1C-(东)x-(南)1D-` → "技术性加倍以后" ✓

### 序列分析与双人/四人模式无关

**问题**: `_get_bidding_str_for_keyword()` 在分析过程中做了补全，违反了"序列分析过程必须和双人/四人叫牌无关"的原则
**修复** (`main.py`):
- 移除补全逻辑，`_get_bidding_str_for_keyword()` 直接返回原始序列
- 序列分析过程与双人/四人模式无关

### 预处理结果为空时自动切换优化

**问题**: 切换到"成局与满贯"的条件检查 `has_structure`，但"成局与满贯"是描述性约定，没有结构化叫品
**修复** (`main.py`):
- 修改切换条件：只要"成局与满贯"有内容就切换
- `if slam_result["original_content"]:` 而不是 `if slam_result["subsequent_bids"] or slam_result.get("has_structure"):`

### 开叫位置判断优化

**问题**: 当南家开叫pass后，北家实际上是开叫位置，但 `is_opener` 判断只检查序列是否为空
**修复** (`main.py`, `knowledge/loader.py`):
- `is_opener` 判断改为检查序列中是否有非pass叫品
- 预处理逻辑：当序列只包含pass时，也提取开叫叫品

### 代码重构

**问题**: `ai_bid()` 和 `human_bid()` 中后续叫品格式化逻辑重复
**修复** (`main.py`):
- 新增 `_format_subsequent_bids()` 方法：提取公共的后续叫品格式化逻辑
- 更新 `ai_bid()` 和 `human_bid()` 使用新方法

### 双人叫牌关键字提取优化

**问题**: 叫牌序列超过8个叫品时，关键字提取返回"成局与满贯"，浪费了JF约定中实际提供的约定长度
**修复** (`bridge/bidding.py`):
- 新增 `is_pair_bidding` 判断：检查所有偶数位置（索引1,3,5...）是否都是"pass"
- 双人叫牌时，始终返回 `first-third`（不限制长度）

## 2026-02-20

### 历史记录功能修复

**问题**: 历史记录功能无法正常保存和加载，记录显示格式冗长
**原因**:
1. `_ask_save_history` 方法定义了但从未被调用
2. `to_display_string` 在花色为空时不输出，导致解析时位置错乱
3. `mode.value` 可能为 None 导致保存失败

**修复**:
1. `main.py`: 在 `display_final_result()` 后调用 `_ask_save_history()`
2. `bridge/dealer.py`:
   - `to_display_string`: 缺门花色用 "-" 占位，确保四门花色都有输出
   - `parse_hand_string`: 处理 "-" 占位符，正确解析为空字符串
3. `main.py`:
   - `_ask_save_history`: 添加手牌数据检查、mode 空值处理、详细错误输出
   - `view_history`: 同样修复 mode 空值处理和错误输出
4. `utils/history.py`:
   - `format_record_summary`: 简化为单行格式，显示编号、时间、定约、叫牌序列、备注
5. `main.py` - `view_history`:
   - 简化菜单选项：编号查看详情、d+编号删除、l+编号加载、c清空
   - 删除前增加确认提示
   - 加载时同时恢复叫牌序列

### 叫品选择输出格式优化

**问题**: "叫品选择"字段只输出最终叫品，无法看到多个合格叫品时的选择过程；层次型约定和描述性约定定义有灰色地带
**修复** (`llm/prompts.py`, `main.py`):
- 字段重命名："叫品选择" → "选定叫品"（仅输出最终叫品名称）
- 约定类型定义（根据预处理结果判断，消除灰色地带）：
  - 结构化约定：预处理结果不为空（有明确的层次结构可提取）
  - 描述性约定：预处理结果为空（以文字描述为主，无法预处理提取）
- "叫品筛选过程"字段：分三个阶段清晰输出
  - 第一阶段：约定要求筛选
    - 结构化约定：使用预处理结果，有队友建议时合并去重
    - 描述性约定：从JF约定内容中提取叫品选项
    - 备选叫品为空时，主提示词输出"JF无合格叫品"，备用提示词使用自然约定
  - 第二阶段：合规性检查（对满足约定要求的叫品执行叫品递增、重复、加倍合法性检查）
  - 第三阶段：选择最终叫品（按优先级规则选择）

### 预处理逻辑增强

**问题**: 开叫位置和"xx开叫"类型约定无法提取预处理结果
**修复** (`knowledge/loader.py`):
- 新增 `is_opening_keyword()`: 判断是否为开叫类型关键字
- 新增 `extract_opening_bids()`: 从开叫约定中提取顶级叫品（如1C、1D、1H、1S、1NT等）
- 新增 `extract_response_bids_from_opening()`: 从"xx开叫"类型约定中提取应叫叫品（如从"1C-1D"提取"1D"）
- 修改 `preprocess_jf_content()`: 增加对开叫位置和"xx开叫"类型的特殊处理
- 修正正则表达式：`[1-7][CDHSNT]` → `[1-7](?:[CDHS]|NT)` 以正确匹配NT
- 测试结果：
  - 花色开叫（开叫位置）：15个开叫叫品 → 结构化约定
  - 1C/1D/1H/1S/1NT/2C开叫：13-23个应叫叫品 → 结构化约定
  - 阻击叫（2D-3NT开叫）：1-14个应叫叫品 → 结构化约定

### 主提示词简化

**问题**: 描述性约定处理逻辑冗余，且区分结构化/描述性约定无实际意义
**修复** (`llm/prompts.py`):
- 简化叫品筛选过程为两个阶段（原三个阶段）
- 统一处理逻辑：
  - 主提示词：预处理结果 > 队友建议 > 输出"JF无合格叫品"
  - 备用提示词：预处理结果 > 队友建议 > JF约定原文 > 自然约定
- 删除"判断约定类型"步骤，因为即使是结构化约定，叶子节点也提取不到后续叫品
- 主提示词和备用提示词同步修改

### 提示词术语统一

**问题**: "叫品含义及后续建议"字段中仍使用"层次型约定"术语，与当前逻辑不一致
**修复** (`llm/prompts.py`):
- 统一三个提示词（主提示词、备用提示词、人类叫牌提示词）的表述
- 将"层次型约定中没有后续叫品"改为"【预处理提取的后续叫品】中没有选定叫品的后续"
- 保持术语一致：预处理结果包含两级叫品
  - 第一级：当前叫牌的备选叫品
  - 第二级：每个叫品的后续建议选项

### 备用提示词结构性约定判断

**问题**: 备用提示词在结构性约定的叶节点情况下，仍从JF约定原文提取叫品，容易导致AI提取错误内容
**修复** (`knowledge/loader.py`, `llm/prompts.py`, `main.py`):
- 新增 `is_structural_convention()` 函数，判断JF约定是否为结构性约定：
  - 花色开叫、xx开叫、1C-1D型、第三四家1H/1S → 结构性约定
  - 其他约定根据内容是否有缩进层次结构判断
- 预处理结果新增 `is_structural_convention` 字段
- 备用提示词新增"约定类型标识"部分，传递 `{is_structural}` 参数
- 备用提示词叫品筛选逻辑：
  - 预处理结果不为空 → 使用预处理结果
  - 预处理结果为空但有队友建议 → 使用队友建议
  - 预处理结果为空且无队友建议：
    * 结构性约定 → 直接使用自然约定（叶节点，JF无后续）
    * 描述性约定 → 从JF约定原文提取
  - 以上都没有 → 判断联手点力是否≥25点，有希望入局才使用自然约定，否则选择pass
- 删除备用提示词中冗余的"第四阶段：合格叫品列表和最终叫品决策"部分，该逻辑已整合到"叫品筛选过程"字段

### 预处理结果格式优化

**问题**: AI混淆预处理结果的两级叫品，将后续建议误当作备选叫品
**修复** (`main.py`):
- 修改预处理结果格式化逻辑，清晰标注：
  - 第一级：当前玩家的备选叫品
  - 第二级：该叫品的后续建议（供下一轮参考）
- 避免AI将两级叫品混淆

### 预处理提取逻辑修复

**问题**: 
1. 当队友叫品缩进级别为0时，错误提取了后续所有缩进级别0的叫品（开叫人的其他再叫分支）
2. 当队友叫品所在行是关键字行（如"2C-2NT"包含多个叫品）时，无法提取后续叫品

**修复** (`knowledge/loader.py`):
- 删除 `extract_subsequent_bids` 中错误的特殊处理逻辑
- 当遇到缩进≤队友叫品时立即停止提取
- 新增关键字行判断：当队友叫品行缩进为0且包含≥2个叫品时，提取后续所有顶级叫品（以"├"开头）
- 测试结果：
  - 1D-1H-2NT后正确提取4个叫品（3C、3D、3H、3S）
  - 2C-2NT后正确提取6个叫品（3C、3D、3H、3S、3NT、4C）

### 历史记录功能修复

**问题**: 
1. 历史记录菜单的 print 语句缺少 `flush=True`，可能导致输出不显示
2. 叫牌结束后自动提示保存，不符合用户习惯

**修复** (`main.py`):
- `view_history` 函数所有 print 语句添加 `flush=True`
- 移除叫牌结束后的自动保存提示
- 在历史记录菜单中添加 "s - 保存当前牌局" 选项
- 用户可以在历史记录菜单中主动保存当前牌局

### 长叫牌序列关键字提取修复

**问题**: 
1. 叫牌序列超过8个叫品时，关键字提取返回"成局与满贯"而不是具体序列
2. 导致预处理结果为空，LLM无法获取后续叫品建议
3. 后续建议格式不清晰，LLM误将叫品含义当作后续建议

**修复** (`bridge/bidding.py`, `main.py`, `llm/prompts.py`):
- 新增 `_extract_keyword_for_long_sequence` 函数处理超过8个叫品的序列
- 识别1NT-2C、2C-2D等常见长序列模式
- 改进预处理结果格式：使用【bid】标记叫品，明确标注后续建议
- 修改主提示词中后续建议的说明，强调后续建议是下一轮队友的备选项

**问题**: 
1. 主提示词逻辑不适合开叫位置（开叫位置没有预处理结果和队友建议）
2. `_is_no_valid_bid()` 错误检测到"JF无合格叫品"字符串，导致已选定叫品仍跳转到备用提示词
3. 开叫位置预处理结果格式不正确（包含"队友xx家最近叫品"）

**修复** (`llm/prompts.py`, `main.py`):
- 主提示词逻辑区分开叫位置和非开叫位置：
  - 开叫位置：从JF约定中提取开叫叫品作为备选
  - 非开叫位置：预处理结果 > 队友建议 > 输出"JF无合格叫品"
- `_is_no_valid_bid()` 优先检查是否已选定有效叫品，避免误判
- 开叫位置预处理结果格式改为"【预处理提取的开叫叫品】"

## 2026-02-19

### 扣叫和问叫规则修复

**问题1**: AI用3S表示草花控制，而不是直接扣叫草花
**修复** (`llm/prompts.py`):
- 新增"扣叫叫品选择规则"：扣叫必须直接叫出有控制的花色
- 例如：有♣A控制，应直接扣叫4♣，而不是扣叫3♠来"表示♣控制"

**问题2**: 扣叫起始点不明确
**修复** (`llm/prompts.py`):
- 新增"扣叫起始点规则"：
  - 高花配合（将牌为H或S）：扣叫从3M的下一阶开始，**不包括将牌本身**
  - 例如：将牌为H时，扣叫从3S开始；将牌为S时，扣叫从4C开始
  - 低花配合（将牌为D或C）：扣叫从3NT以上开始
- 新增"将牌花色不能扣叫"规则：将牌本身就是配合花色，不需要显示控制

**问题3**: 错误添加"问叫答叫例外"规则
**原因**: 误以为问叫后答叫可以违反叫品递增规则
**事实**: 桥牌叫牌永远不允许在高级叫品后叫低级叫品
**修复** (`llm/prompts.py`):
- 删除错误的"问叫答叫例外"规则
- 5H后只能叫5S、5NT、6C...，绝不能叫5D

**问题4**: 5H问将牌Q后答叫5D
**原因**: JF约定"加叫至5阶将牌=无将牌Q"是相对于4NT问叫而言的
**修复** (`llm/prompts.py`):
- 新增"问将牌Q后的答叫规则"：
  - 当问将牌Q的叫品已高于5阶将牌时，答叫必须高于问叫花色
  - 例如：将牌为D，5H问将牌Q后，无Q应答叫6D，而不是5D

**问题5**: AI忽略"自己有将牌Q时不能问Q"的规则
**修复** (`llm/prompts.py`):
- 强化第1条规则标题为"禁止问自己持有的将牌Q（必须严格遵守）"
- 使用加粗强调"绝对不能问将牌Q"
- 明确说明只有没有将牌Q时才能问

### 后续叫品处理规则修复

**问题1**: AI编造不存在的后续叫品列表
**原因**: AI将JF约定中其他分支的内容当作当前叫品的后续建议
**示例**: 1S-2C-2NT后，AI将2D分支下的后续叫品（3C、3D、3H等）当作2NT的后续建议
**修复** (`llm/prompts.py`):
- 三个提示词（主提示词、备用提示词、人类叫牌提示词）都添加禁止规则：
  - `**禁止编造后续叫品列表**`
  - `**禁止将JF约定中其他分支的内容当作当前叫品的后续建议**`
- 当预处理结果为空时，必须明确说明"无后续叫品列表"

**问题2**: AI跳过JF约定中的合格叫品
**原因**: AI以"速达原则"为由跳过约定，选择自然约定的叫品
**示例**: 2NT问叫后，AI找到合格叫品3H，却跳过选择4S
**修复** (`llm/prompts.py`):
- 备用提示词新增"JF约定优先原则"：
  - `如果JF约定中存在合格叫品，**必须从中选择**`
  - `速达原则、逼局进程等策略都不能作为跳过JF约定的理由`
- 自然约定处理改为"仅当JF约定都没有提供合格叫品时"才能使用

**问题3**: AI在"叫品选择"阶段选择不在合格列表中的叫品
**原因**: "叫品选择"字段没有强制要求从合格列表中选择
**示例**: 叫品筛选过程找到合格叫品3H，但叫品选择输出4S
**修复** (`llm/prompts.py`):
- 主提示词和备用提示词都新增第1条规则：
  - `**【必须从合格叫品中选择】**：最终叫品必须从"叫品筛选过程"中输出的合格叫品列表中选择`
  - `**禁止选择不在合格列表中的叫品**，即使该叫品符合自然约定或其他策略`

**问题4**: 主提示词无法处理描述性约定
**原因**: 主提示词逻辑：预处理为空 + 队友建议为空 → 输出"JF无合格叫品"
**示例**: 1C开叫后的应叫，JF约定是描述性格式，预处理无法提取后续叫品
**修复** (`llm/prompts.py`):
- 主提示词新增"描述性约定处理"：
  - `如果预处理结果为空，说明JF约定可能是描述性约定`
  - `从JF约定内容中提取叫品选项，例如"1C-1D：6点以上，4+D"表示1D是一个叫品选项`
  - `将提取的叫品作为备选叫品，使用**刚性规则**逐一验证`
- 修改权限限制条件：只有当JF约定内容中也没有找到叫品选项时，才输出"JF无合格叫品"

**问题5**: 预处理"1C-1S"返回空结果
**原因**: JF约定格式特殊：
- 第一行"1C-1S后的进程"包含所有叫品，导致`skip_count >= len(bids)`
- 后续叫品（如"├1NT"）缩进为0，与关键字行缩进相同
- `extract_subsequent_bids`期望`target_indent = partner_indent + 1`，但实际缩进为0
**修复** (`knowledge/loader.py`):
- `find_partner_bid_in_content`: 当`skip_count >= len(bids)`时，找到第一个包含叫品的行
- `extract_subsequent_bids`: 新增处理缩进为0且以"├"开头的后续叫品

**问题6**: 图形化显示叫牌顺序混乱
**原因**: 原逻辑根据叫牌位置来划分轮次，但未正确处理开叫者之前的位置
**示例**: 北家开叫时，第一行显示"2NT PASS 1S PASS"，但南和西应该在第一行留空
**修复** (`bridge/output_format.py`):
- 采用Nx4表格模型：列固定为South/West/North/East
- 从开叫者位置开始填充，开叫者之前的列保持空白
- 填满一行后自动换行继续填充

### Deep Finesse格式缺门处理修复
**问题**: 提供给Deep Finesse校验的文件中缺门花色位置错误
**原因**: 
- `df_format_to_hand` 把 "-" 转换为空字符串 ""
- `hand_to_df_format` 用 `split()` 处理时空字符串被吃掉
- 结果：`"J8 - AK972 K87543"` → `"J8 AK972 K87543 -"`（缺门位置错乱）

**修复** (`bridge/deep_finesse.py`):
- `df_format_to_hand`: 保持 "-" 不变
- `hand_to_df_format`: 正确识别并保留 "-"

### 单叫品关键字预处理修复
**问题**: "第三四家开叫1H"等单叫品关键字无法正确提取后续叫品
**原因**:
- 标题行 "5.8 第三四家开叫 1 高花" 不包含叫品
- `first_line_bids = []`，`is_single_bid_keyword = False`
- 搜索1S时 `target_indent=1`，但1S实际是 `indent=0`

**修复** (`knowledge/loader.py`):
- 当第一行没有叫品且 `skip_count=0` 时，向下查找包含单个叫品的行
- 如果找到且该叫品匹配叫牌序列的第一个叫品，则识别为单叫品关键字

### 主提示词AI权限限制加强
**问题**: 主提示词AI在预处理和队友建议都为空时自行决定叫品
**修复** (`llm/prompts.py`):
- "叫品筛选过程"添加 `**【主提示词AI权限限制】**` 标记
- 明确规定：即使逼局也不能自行决定叫品，必须输出"JF无合格叫品"

### 禁止暴露实际信息规则加强
**问题**: 叫品含义暴露了实际点力和牌型（如"点力12点，牌型为2-1-6-4"）
**修复** (`llm/prompts.py`):
- 三个提示词都添加 `**【禁止暴露实际信息】**` 标记
- 只能引用约定中的范围（如"10-12点"），禁止暴露实际值

### bid_meanings后续建议处理优化
**问题**: 南家收到的是自己之前叫牌的后续建议，而不是队友的
**原因**: `bid_meanings` 累积了所有叫品的完整信息，包括后续建议
**修复** (`main.py`):
- 双人模式：只保留最后一个叫牌的后续建议
- 四人模式：保留两个队伍各自的后续建议（南北队和东西队分别保留）
- 每次追加新叫牌时，删除同队伍旧的后续建议

### 叫牌含义显示优化
**修复** (`main.py`):
- 在"全部格式"输出模式下，叫牌含义显示在图形化布局和紧凑型布局之间
- 显示时删除"1. **叫品含义**："和"2. **后续建议**："等标签
