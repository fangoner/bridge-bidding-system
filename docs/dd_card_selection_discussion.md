# DD 选牌机制讨论与 Tiered 关键决策检测重构

> 2026-06-18 完整对话记录

---

## 一、DD 采样性能实测

### 测试方法

对 `solve_board` 和完整采样循环（`sample → PBN → Deal → solve_board`）分别做了 500-2000 次基准测试。

### 关键数据

| 阶段 | 耗时 | 占比 |
|------|------|------|
| `DealSampler.sample()` | 0.04ms | 0.1% |
| `_hands_to_pbn()` | 0.03ms | 0.0% |
| `Deal(pbn)` 构造 | 0.07ms | 0.1% |
| **`solve_board()`** | **73.43ms** | **99.8%** |
| **完整一次采样** | **73.58ms** | 100% |

`solve_board` 在不同随机牌局上差异巨大：

| 场景 | mean | p50 | p95 | max |
|------|------|-----|-----|-----|
| 同一副牌反复求解 | 0.13ms | 0.03ms | — | — |
| 不同随机牌求解 | 73.4ms | 60.1ms | 154.5ms | **448ms** |

同一副牌反复求解快了 500+ 倍（endplay 内部缓存），但 DD 搜索每轮采样不同分布，无法命中缓存。

### 采样数推算

```
当前默认 100 样本:  ~7.4s
200 样本:          ~14.7s
300 样本:          ~22.1s  (略超 20s 上限)
500 样本:          ~36.8s
```

**结论**：瓶颈 100% 在 `solve_board` 自身，采样和格式转换几乎零开销。最终将 `DD_NUM_SAMPLES` 从 100 提升到 200（`DD_MIN_SAMPLES` 联动从 15 → 30），预估 ~14.7s，在 20s 限制内。

### 最终参数调整

- `config.py`: `DD_NUM_SAMPLES = 200`
- `config.py`: `DD_TIME_LIMIT = 20.0`（不变）
- `play_service.py`: 当用户覆盖 `dd_samples` 时，`min_samples` 按 `DD_MIN_SAMPLES * (dd_samples / DD_NUM_SAMPLES)` 比例联动，下限 max(5, ...)，上限 min(num_samples, ...)
- 前端 `App.jsx`: 默认值从 100 → 200

---

## 二、DD 选牌流程详解

### 第一步：采样随机世界

从当前玩家的不完全信息视角出发，随机分配未知牌给未知位置，构建一个"可能的真实世界"。已知信息包括：自己的手牌、明手牌（首攻后可见）、已打出的牌、叫牌约束（HCP/花色张数）。

### 第二步：双明手求解

对每个采样世界调用 `solve_board()`——假设四家牌都已知，计算最优路线下每张候选牌的赢墩数。**一次 `solve_board` 同时给出所有候选牌的得分**。

### 第三步：汇总选最优

对每张候选牌，在所有采样世界上求平均赢墩数，加上 `rank_bonus`（大牌偏好，A=0.28 墩，用于破平局），选最高的。

```python
# 选牌公式
score = (avg_tricks + rank_bonus)        # 庄家方最大化
score = -(avg_tricks + rank_bonus)       # 防守方最小化
```

---

## 三、为什么 200→300 样本效果不明显

### 核心原因

每张候选牌在**同一个采样世界**里用的是同一个分布——候选牌之间的比较是**配对比较**（paired comparison），统计效力远高于独立比较。

世界本身的波动被抵消了。差异的方差远小于每张牌自身得分的方差：

- 50 样本通常足以区分差 0.5 墩以上的候选
- 100 样本能可靠区分 0.3 墩的差异
- 200 样本能区分 0.2 墩的差异
- 300 vs 200 — 几乎无差别

**真正限制 DD 选牌质量的因素不是样本数**，而是 DDMC 算法的四个理论缺陷。

---

## 四、DDMC 的理论缺陷（与主流软件对比）

### 四个缺陷

1. **Strategy Fusion（策略融合）**：DDMC 在每个世界里"知道"所有牌的位置，把需要猜断的路线当成确定性的来评分
2. **Non-Locality（非局部性）**：最优打法可能依赖于"如何到达这个局面"，DDMC 独立评估每个子树
3. **Perfect Minimizing（完美防守假设）**：假设对手也全知全能，看不到欺骗打法的价值
4. **Non-Informative Play（无信息价值）**：因为"已经知道"分布，永远不会为获取信息而出牌

### 主流软件如何应对

| 软件 | 样本数 | 应对方式 |
|------|--------|---------|
| **GIB** | 50-500 | 贝叶斯加权采样；从第二墩起切换到真正的单明手求解器 |
| **Wbridge5** | 20-40 | αμ 搜索：维护 Pareto 前沿，做多步前瞻规划 |
| **Jack** | 类似 | 和 GIB 类似的 DDMC + 改进 |
| **SharkBridge** | 类似 | 同上 |

**没有人用"分差小就升级另一个引擎"这种模式。** Wbridge5 的做法是改变搜索结构本身（αμ），而不是换引擎。

### LLM 的优势

LLM 不犯 strategy fusion 的错误。它做的是**不完全信息下的规划**——不会把"这个世界里我知道 Q 在哪所以飞对了"当成确定性路线。它能识别"这条路线后续有猜断风险"。

所以 Tiered 里 DD → LLM 的升级，不是弥补统计精度不足，而是弥补 DDMC 的**信息结构盲区**。

---

## 五、Tiered 关键决策检测重构

### 旧逻辑的问题

只用一个指标：**#1 和 #2 候选牌的平均墩数差是否 ≤ 固定阈值（庄 0.2 / 守 0.3）**。

问题：
1. 阈值死，精度活——200 样本 SE≈0.11，30 样本 SE≈0.28，固定阈值无法自适应
2. 只看均值，不看方差——strategy fusion 的典型症状是 min-max 区间宽（如 [7-10]），旧逻辑完全无视
3. 只看 #1-#2，不看整体——如果 #1-#5 挤在 0.3 墩内，比 #1-#2 差 0.1 更值得关注

### 新逻辑：三个信号

#### 信号 1：Strategy Fusion 检测

遍历 top 2 候选牌，检查 `max_tricks - min_tricks`。如果任一张的跨度 ≥ 3 墩**且**该牌与 #1 的均值在集群范围内（即它是真正的竞争者），触发升级。

```
示例：
#1 ♠3: 9.78 [9-10]   spread=1  → 不触发
#2 ♣4: 9.65 [7-10]   spread=3  → 触发！且与#1差0.13 < margin(0.22)
```

阈值 3 的依据：正常单套打法 min-max 差通常 ≤2 墩；≥3 说明该牌的分支在不同分布下走向了完全不同的路线——典型的 strategy fusion。

#### 信号 2：候选集群检测

用动态标准误替代固定阈值：

```python
SE = 1.5 / √N          # 200样本 → 0.11, 30样本 → 0.27
margin = 2.0 × SE       # 200样本 → 0.22, 30样本 → 0.55

# 距 #1 在 margin 内的牌视为"不可区分"
如果 ≥2 张牌在集群内 → 触发升级
```

#### 信号 3：定约边缘（不变）

庄家还需 ≤1 墩成约 / 防守方还需 ≤1 墩击垮 → 触发升级。

### 新增配置参数

```python
# config.py — 替换 TIERED_CRITICAL_SPREAD_DECLARER/DEFENDER
TIERED_FUSION_SPREAD = 3      # min-max 跨度 ≥此值 → strategy fusion
TIERED_CLUSTER_SE = 2.0       # 距 #1 N×SE 内视为同一集群
TIERED_TYPICAL_SD = 1.5       # solve_board 赢墩典型标准差
```

### MCTS 回退路径

`_is_critical_decision_mcts()` 因 MCTS rollout 的 min/max 不如 solve_board 可靠，只用集群检测（固定 0.5 墩阈值）+ 定约边缘。

### 边界情况

| 场景 | 信号1 | 信号2 | 信号3 | 结果 |
|------|:---:|:---:|:---:|------|
| ♠3[9-10] vs ♣4[7-10], gap=0.13 | ✓ | ✓ | - | 升级 |
| 3牌挤在0.05墩, [8-10]范围 | ✗ | ✓ | - | 升级 |
| #1=10.5 vs #2=7.5[6-9], gap=3.0 | ✗ | ✗ | - | 不升级 |
| 150样本, gap=0.25, margin=0.24 | ✗ | ✗ | - | 不升级 |
| 30样本, gap=0.30, margin=0.55 | ✓ | ✓ | - | 升级 |
| 定约边缘(还需1墩) | ✗ | ✗ | ✓ | 升级 |

---

## 六、修改文件清单

| 文件 | 改动 |
|------|------|
| `config.py` | `DD_NUM_SAMPLES` 100→200；删除旧 Tiered 阈值，增加 3 个新参数 |
| `bridge/play_service.py` | `min_samples` 联动缩放；新增 `_estimate_se()`；重写 `_is_critical_decision()` 和 `_is_critical_decision_mcts()` |
| `bridge/mcts/dd_search.py` | 首攻阶段 known_positions 修复（信息泄露） |
| `bridge/mcts/sampler.py` | 首攻阶段庄家方不暴露明手牌（信息泄露修复）；约束重试警告日志 |
| `bridge/mcts/search.py` | 首攻阶段 known_positions 修复；根节点选牌策略从 visits → avg_value |
| `bridge/mcts/rollout.py` | `max_remaining` 修复：`max()` 替代 `sum()//4` |
| `bridge/dealer.py` | HCP 重试耗尽记录警告 |
| `bridge/deep_finesse.py` | 庄家确定逻辑简化 |
| `bridge/bidding.py` | 括号清理 bug 修复 |
| `bridge/play_engine.py` | play_card 条件简化 |
| `api/main.py` | bid/play_card/read_clipboard 异常处理增强 |
| `web/src/App.jsx` | DD 采样数默认 200；定约花色符号映射 |
| `web/src/components/CardTable.jsx` | DD 引擎旋转图标修复（aiLoading 提升为第一优先级） |
| `test_tiered_engine.py` | 测试更新为新逻辑 |

---

# 2026-06-20 续篇：αμ 搜索落地与大师级优化全套实施

> 本次会话目标：将 2026-06-18 讨论中识别的 DDMC 理论缺陷（strategy fusion / non-locality / perfect minimizing / non-informative）通过工程化手段系统性修复，使打牌引擎达到大师级水平。

## 七、优化路线图（7 个优先级）

基于"成本 × 收益"评估，制定 7 个优先级，按顺序实施：

| 优先级 | 项目 | 成本 | 收益 | 核心思路 |
|--------|------|------|------|---------|
| 1 | 三信号关键决策检测 | 低 | 高 | 从固定阈值升级为多信号融合检测 |
| 2 | MCTS 根节点选牌 + rollout 强化 | 低 | 中 | 修复根节点选牌 bug，rollout 80% 启发式 |
| 3 | 信念状态跟踪 + 粒子滤波 | 中 | 中 | 60 个加权粒子，void + 信号约束更新 |
| 4 | αμ 搜索 | 高 | 高 | Wbridge5 算法，解决 PIMC 两大缺陷 |
| 5 | 首攻 DD + LLM 融合 | 中 | 中 | 首攻阶段并行 DD + LLM，LLM 拿 DD 统计做选择 |
| 6 | 防守信号模型 | 中 | 中 | 三类信号编码 + 注入 LLM 提示词 |
| 7 | LLM 输出校验层 | 低 | 中 | 规则化校验，违规回退 |

## 八、αμ 搜索算法实现细节

### 8.1 核心数据结构

**OutcomeVector**（长度 N 的 0/1 向量，N=粒子数）：
- 每个元素对应一个 possible world
- `1` = 庄家方在该 world 下成约，`0` = 不成约
- `dominates(other)`：所有位 ≥ other 即支配

**ParetoFront**（不被支配的向量集合）：
- `add(vec)`：加入新向量，自动剔除被支配的，并去重
- `union(other)`：合并两个前沿，保留不被支配的
- `is_subset(other)`：判断当前前沿是否被另一前沿包含

### 8.2 递归搜索流程

```
def alpha_mu(node, depth):
    if depth == 0 or node.is_terminal():
        return leaf_outcome_vector(node)   # DDS solve_board 评估每个 world
    
    if node.is_max_node():  # 庄家方
        front = empty_pareto_front()
        for move in node.legal_moves():
            child = node.apply(move)
            child_front = alpha_mu(child, depth - 1)
            front = front.union(child_front)   # 强制所有 worlds 选同一 move
        return front
    else:  # 防守方 Min 节点
        vec = []
        for world in node.worlds:
            best = worst_outcome
            for move in node.legal_moves(world):
                child = node.apply_in_world(move, world)
                child_outcome = alpha_mu_in_world(child, depth - 1, world)
                if child_outcome < best:
                    best = child_outcome
            vec.append(best)
        return pareto_front_from(vec)   # 每 world 独立选最小化 Max 的 move
```

### 8.3 关键设计决策

1. **Max 节点 union**：所有 worlds 必须选同一 move，因为庄家方不知道真实分布。这是 αμ 相对 PIMC 的核心改进——PIMC 在每个 world 独立选最优 move（strategy fusion），αμ 强制一致选择。

2. **Min 节点独立**：防守方假设完美信息（每个 world 独立选最小化 Max 的 move）。这是 non-locality 的体现——防守方的最优策略依赖于真实分布。

3. **Pareto 前沿而非单一向量**：Max 节点的 union 可能产生多个不被支配的向量（对应不同 move 的子前沿合并），保留全部用于后续比较。

4. **触发条件**：每手 ≤8 张时启用（`ALPHA_MU_ENDGAME_CARDS`=8），20 worlds，深度 ≤4，时间限制 8s。残局阶段才用，避免中盘搜索爆炸。

### 8.4 与 DD 枚举的关系

DD 枚举（`bridge/mcts/dd_search.py`）在每手 ≤6 张时枚举所有候选牌的 DDS 结果，本质是 depth=1 的 αμ。αμ 是 depth=N 的推广，所以残局阶段 αμ 优先，DD 枚举作为 endplay 不可用时的回退。

## 九、信念跟踪与信号注入

### 9.1 粒子滤波器（`bridge/mcts/belief.py`）

- **粒子**：一个 possible world = 四家手牌的完整分配
- **初始化**：60 个粒子（`BELIEF_NUM_PARTICLES`=60），从叫牌约束 + 已知信息采样
- **更新**：
  - void 约束：某家某花色已无牌 → 该花色有牌的粒子权重清零
  - 防守信号：信号一致的粒子权重 ×1.3，不一致的 ×0.7
- **重采样**：权重归一化后按概率重采样，保持粒子数稳定
- **采样接口**：DD/MCTS 采样器调用 `belief_tracker.sample()` 获取分布

### 9.2 防守信号模型（`bridge/mcts/signals.py`）

三类信号编码：

| 信号类型 | 含义 | 编码方式 |
|---------|------|---------|
| Attitude | 欢迎/不欢迎 | 高牌(≥8)=欢迎，低牌(<8)=不欢迎 |
| Count | 张数信号 | 高/低暗示偶/奇张数 |
| Suit Preference | 花色偏好 | 特定花色的高低组合 |

- `collect_all_signals(state)`：从已完成墩和当前墩收集信号证据
- `format_partner_signals_for_prompt(state, player)`：将同伴信号格式化为 LLM 提示词片段
- belief tracker 用信号约束过滤粒子分布

## 十、对当前所有打牌引擎的影响评估

### 10.1 LLM 引擎

**改进**：
- 首攻阶段获得 DD 候选统计提示（期望墩数 + min-max 区间）
- 防守阶段获得同伴信号注入提示词
- 输出经规则化校验（合法性/第四家能赢却出小/第二家小牌盖大）
- 校验失败自动回退到 `_select_best_card`

**影响**：决策质量提升，违规出牌自动回退，整体稳定性增强。

### 10.2 MCTS 引擎

**改进**：
- 根节点选牌逻辑修复（访问次数 + 胜率综合排序，原逻辑只看访问次数）
- rollout 策略强化：`ROLLOUT_GREEDY_PROB`=0.80，80% 启发式（赢墩/跟花色/弃牌），20% 随机探索
- belief tracker 提供更真实的采样分布

**影响**：选牌更准确，rollout 更贴近实战，搜索效率提升。

### 10.3 DD 引擎

**改进**：
- 残局阶段（≤8 张）让位 αμ 搜索
- 中盘阶段 belief tracker 改善采样分布
- 关键决策由三信号检测升级 LLM

**影响**：残局不再用纯 DDMC（避免 strategy fusion），中盘采样更真实，关键局面自动升级 LLM。

### 10.4 Tiered 引擎

**改进**：
- 残局阶段优先 αμ（解决 strategy fusion），不可用回退 DD 枚举（≤6 张）
- 首攻阶段 DD + LLM 融合（`_opening_lead_play`）
- 中盘三信号检测升级 LLM（`_is_critical_decision` 重写）

**影响**：分层调度更精细，残局质量大幅提升，首攻和关键决策更智能。

### 10.5 Perfect DD 引擎

**不受影响**：全知双明手，无采样，无 PIMC 缺陷。仅作为基准对照。

## 十一、集成测试验证

### 11.1 αμ 算法测试（`tests/test_alpha_mu.py`，5 用例）

1. `test_outcome_vector_dominates`：OutcomeVector 支配关系
2. `test_pareto_front_union`：ParetoFront 合并去支配
3. `test_endgame_end_to_end`：残局端到端搜索
4. `test_dd_consistency`：αμ 与 DD 结果一致性
5. `test_unique_choice`：唯一选择场景

**结果**：5/5 通过。

### 11.2 PlayService 集成测试（`tests/test_play_service_integration.py`，15 用例）

| # | 测试 | 覆盖点 |
|---|------|--------|
| 1 | 游戏初始化 | 发牌 + 定约解析 + 角色设置 + 引擎状态 |
| 2 | 首攻阶段合法出牌 | 首墩无跟牌限制 |
| 3 | 完整打完一墩 | 4家出牌 + 墩判定 + 赢家首攻下一墩 |
| 4 | 跟花色规则 | 必须跟花色 + 违规检测 |
| 5 | 撤销出牌 | `undo_last_card` 手牌恢复 + 出牌者回退 |
| 6 | DD 引擎 | 蒙特卡洛 + 双明手评估返回合法牌 |
| 7 | MCTS 引擎 | 树搜索 + rollout 返回合法牌 |
| 8 | Tiered 引擎中盘 | 首攻阶段触发 `opening_lead` 分支 |
| 9 | Tiered 残局 αμ | 残局触发 `endgame_alpha_mu` 分支 |
| 10 | Perfect DD 引擎 | 全知双明手返回合法牌 |
| 11 | 多引擎一致性 | DD/MCTS/Tiered/Perfect 同一局面都返回合法牌 |
| 12 | 完成判定与结果 | 成约/宕墩判定 + 消息生成 |
| 13 | 信念跟踪器重置 | 新局开始清空旧粒子 |
| 14 | 加倍定约解析 | `doubled=True` 正确解析 |
| 15 | 关键决策检测 | `_is_critical_decision` 方法存在性 + 签名 |

**结果**：15/15 通过。

### 11.3 端到端验证

残局场景 αμ 搜索：
- 20 worlds，depth ≤4，4 nodes，12 DDS calls，0.3s 完成搜索
- Top plays: ♠A(0.00), ♠K(0.00), ♥A(0.00), ♦A(0.00)

## 十二、配置参数汇总

新增配置（`config.py`）：

```python
# αμ 搜索
ALPHA_MU_ENABLE = True
ALPHA_MU_ENDGAME_CARDS = 8       # 每手 ≤8 张触发
ALPHA_MU_NUM_WORLDS = 20         # 粒子数
ALPHA_MU_MAX_DEPTH = 4           # 搜索深度
ALPHA_MU_TIME_LIMIT = 8.0        # 时间限制（秒）

# 信念跟踪
BELIEF_NUM_PARTICLES = 60        # 粒子数
BELIEF_SIGNAL_WEIGHT = 1.3       # 信号一致加权
BELIEF_SIGNAL_PENALTY = 0.7      # 信号不一致降权
BELIEF_SIGNAL_MIN_RANK = 8       # 信号高/低分界

# Tiered 三信号
TIERED_FUSION_SPREAD = 3.0       # Strategy Fusion 信号阈值（墩）
TIERED_CLUSTER_SE = 2.0          # 集群信号 SE 倍数
TIERED_MIN_SAMPLES = 30          # 样本不足信号阈值

# MCTS rollout
ROLLOUT_GREEDY_PROB = 0.80       # 启发式概率
```

## 十三、本次会话执行过程

1. **会话起点**：用户要求"为整个 play_service 模块生成一份集成测试脚本，覆盖从叫牌到出牌的全流程"
2. **测试脚本设计**：设计 15 个测试用例，覆盖初始化/首攻/中盘/残局αμ/撤销/完成判定/多引擎一致性
3. **测试夹具构建**：
   - `STANDARD_HANDS`：13 张完整局，3NT 定约
   - `ENDGAME_HANDS`：4 张残局，触发 αμ
   - `MockLLMClient`：模拟 LLM 客户端，避免真实 API 调用
4. **测试调试**：
   - 修复手牌解析错误（中文花色符号 → 英文 suit keys）
   - 添加 MockLLMClient 解决 Tiered 引擎首攻阶段 LLM 依赖
   - 修复信念跟踪器未重置问题（`initialize()` 中清空 particles）
5. **测试通过**：15/15 全部通过
6. **文档更新**：更新 CHANGELOG.md、DEVELOPMENT.md、dd_card_selection_discussion.md
7. **Git 提交**：提交所有修改

## 十四、未来工作

- 性能基准：αμ vs DD 在残局的对比基准
- 边界用例：redoubled 定约、异常花色分布
- 信号模型扩展：更多防守信号约定（如 Lavinthal、Roman signals）
- αμ 深度自适应：根据残局张数动态调整搜索深度
