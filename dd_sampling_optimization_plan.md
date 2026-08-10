# DD 提速 & 采样优化 - 现状总结

> 记录 DD 提速与采样优化的最终结论与落地状态，供后续会话参考，避免重复研究已否决的路径。

- 状态：已落地
- 涉及子系统：`bridge/mcts/direct_dds.py`、`bridge/mcts/sampler.py`、`bridge/mcts/dd_search.py`、`bridge/mcts/alpha_mu.py`

---

## 1. 结论一览

| 优化 | 状态 | 说明 |
|------|------|------|
| DDS 并行吃满多核 | ✅ 已落地 | `SetMaxThreads(cpu_count)`，线程 1→8 时单样本 109ms→25ms（约 4×） |
| DD 生成式定向发牌 | ❌ 已否决并回退 | 固定取牌顺序引入采样偏见；历史上 v1.47 已因同类问题废弃过偏置采样 |
| 采样保持均匀 | ✅ 已恢复 | DD / αμ / MCTS 统一走 `DealSampler.sample_n` 均匀采样 + L1/L2/L0 回退链 |
| 可满足性预检（B） | ✅ 已落地 | 进入 L1/L2 前检查约束是否可能成立，不可能则跳过空转 |
| 兜底降级保护（A） | ✅ 已落地 | 兜底从"纯随机"改为"选违反约束最少的候选世界" |
| 世界完整性保证 | ✅ 已落地 | `_sample_uniform` 逐张分配 + 残留退回补齐，每张牌都分配、绝不丢牌 |
| MH 引导式修复收敛 | ✅ 已落地 | `_propose_swap` 补花色移出最高 HCP 非目标牌，避免 HCP 升高被接受率拒绝 |

---

## 2. DDS 并行（已落地）

`direct_dds.py::_load_dll()` 在 DLL 加载成功后调用库导出的 `SetMaxThreads(int)`：

```python
dll.SetMaxThreads.argtypes = [ctypes.c_int]
dll.SetMaxThreads.restype = ctypes.c_int
dll.SetMaxThreads(max(1, os.cpu_count() or 1))
```

- `_dll_lock` 仍串行化所有顶层 DDS 调用，`SetMaxThreads` 只作用于单次求解内部的 OpenMP 线程，无并发冲突。
- 实测线程 1→8：单样本 109ms → 25ms。
- **性能"下降"澄清**：早期 0.5ms/样本是 DDS 对重复牌局的内部缓存假象，真实满局基线约 27ms/样本，非代码回归。

---

## 3. 定向发牌为何被否决（关键教训）

**不要在 DD 上重做定向/偏置采样。**

- 定向采样按固定顺序（南→西→北→东）取牌，无约束位置会优先抢走高 HCP 牌，导致有约束位置（如北需 16-19 HCP）难以满足约束，产生系统性采样偏见。
- 该问题在 v1.47 已发现并废弃过偏置采样；08-09 重试同样失败，已彻底回退。
- DD 的"样本"与 αμ 的"世界"由同一份 `sample_n` 均匀采样生成，仅评估方式不同（DD 蒙特卡洛统计，αμ 联合评估）。保持统一。

**均匀采样下的方向**：通过"降低回退空转 + 改善兜底质量"来优化，而非改变生成方式。

---

## 4. 采样优化（已落地）：可满足性预检 + 兜底降级保护

### 回退链现状（`sampler.py::_sample_one`）

```
可满足性预检 → L1(硬约束,50次) → L2(放宽,50次) → L0(仅void,20次) → 兜底
```

### 4.1 可满足性预检（B）

`_check_feasible(active_constraints, known_info)`：进入 L1/L2 前用当前未知牌池做**必要条件**检查：
- 各位置 `min_hcp` 之和 ≤ 牌池总 HCP
- 各位置 `min_controls` 之和 ≤ 牌池总控制数
- 各位置对某花色的 `suit_min` 之和 ≤ 该花色剩余张数
- 单位置 `suit_min` ≤ 该花色剩余张数
- `specific_cards` 仍存在于未知牌池

任一不满足 → 约束必不可能成立 → 记录 `INFEASIBLE→0` 并跳过 L1/L2 空转，直接进入 L0。

### 4.2 兜底降级保护（A）

`_pick_least_violating(active_constraints, known_info, k=10)`：约束无法满足时的兜底，从"直接返回随机世界"改为：
1. 生成 k 个均匀候选世界；
2. 用 `_constraint_violation_score` 对每个位置打分（HCP/min/max、控制数、花色上下限、exact_suit、balanced、specific_cards）；
3. 返回总违反分数最小的世界。

效果（实测）：南要求 20 HCP 时，兜底候选违反分 0，而单次随机平均 9.3，评估起点更贴近叫牌信息。

### 4.3 与既有删除逻辑的关系

残局枚举阈值统一为 4 张/每手（`DD_ENDGAME_CARD_THRESHOLD=4`，`dd_search.py` 默认参数已对齐）。残局约束扣减后剩余 HCP 在每手 ≤10 张时难以满足 L1，故枚举须晚触发（≤4 张）避免组合爆炸。

### 4.4 世界完整性保证（08-10 落地）

**问题**：中局（trick=2）采样 54.37s 生成 924 个世界，DDS 仅判 16 个有效。根因是旧 `_sample_uniform`"先跳过 void 花色牌→事后回填"策略：当多家共享同一 void 或单家大量 void 时，回填找不到接收位置就**静默丢牌**，产生不完整世界（缺牌/重复）→ DDS 拒绝。

**修复**：`_sample_uniform` 改为逐张分配，保证世界永远完整：
- Tier 1：打乱牌池，每张牌优先放入「仍缺张 + 不 void 该花色 + 剩余需求最大」的位置
- Tier 2：残留牌（花色在几乎所有缺张位都被 void）退回仍缺张的位置补齐张数
- 违反 void 的世界由上层验证链（L0/兜底）剔除，而不是在采样时丢牌

**验证**：西 void♥♦、西&东 void♦ 场景，不完整世界从 200/200 → 0/200；DDS 求解成功率 0/50 → 50/50。

### 4.5 MH 引导式修复收敛（08-10 落地）

**问题**：高 HCP + 花色约束场景（如西 ♠=6 且 HCP 6-10，北 16-19 均型）MH 收敛失败。根因：补花色时移出**最低 HCP** 非目标牌、补入高 HCP 目标牌，导致 HCP 升高被 Metropolis 接受率 `min(1, exp(-beta*(new-old)))` 拒绝。

**修复**：`_propose_swap` 分支 3 补花色时改移出**最高 HCP 非目标花色牌**，使补花色同时降低 HCP（`new_score <= old_score`，接受率=1）；并将 `exact_suit` 低于精确值纳入花色缺长引导。

**验证**：高 HCP ♠ 场景 MH 成功率从 0% → 32%。

### 4.6 可行性预检增强（08-10 落地）

`_position_hcp_feasible` 合并 `suit_min` 与 `exact_suit` 为各花色必需张数，计算 HCP 可达区间时排除 `exact_suit` 花色的剩余牌，准确识别"花色约束迫使 HCP 超标"的不可行场景（如池中 ♠ 仅 5 张却需 6♠）。验证：不可行场景 `_sample_one` 耗时从 2.8s → 23ms/样本。

### 4.7 MH 死锁修复：补花色时保 HCP（08-10 落地）

**问题**：分支 3 统一"移出最高 HCP 非目标牌"解决了 HCP 超标场景，但当违约位置 HCP 恰好压在下限且花色缺长时，补花色扔掉高 HCP 非目标牌把 HCP 跌破下限，产生新的 `min_hcp` 违约被 Metropolis 拒绝，来回振荡死锁，MH 成功率仅 ~19-43%。

**修复**：`_propose_swap` 分支 3 自适应保 HCP——当"移出最高非目标牌 + 补入最低目标牌"会跌破 `min_hcp`（`vhcp - max_non_wanted < vcon.min_hcp`）时，切换为移出**最低 HCP 非目标牌**、补入**最高 HCP 目标牌**（不超出 `max_hcp`）。

**验证**：死锁场景（西 ♠≥6 且 min_hcp=6）MH 成功率 19% → 100%；带 `max_hcp` 上下限场景 100%。回归测试 `test_mh_fix.py`。

### 4.8 MH 多约束收敛：补花色保护边缘花色（08-10 落地）

**问题**：多约束叠加场景（同时要求 HCP + 多花色 + 牌型）MH 成功率低——逆叫16+（♥≥5 且 ♦≥4 且 HCP≥16 非均）仅 50%，技术性加倍 76%。诊断失败样本发现 HCP/牌型基本满足，只差一门花色却卡住。

**根因**：分支3 补花色选"最高 HCP 非目标牌"移出时，常选中恰好 = `suit_min` 的边缘花色（如 ♥=5），补 ♦ 把 ♥ 压到 4 破坏 `♥≥5`，形成"补♦破♥"振荡。分支1 已有 `protected` 逻辑，分支3 缺失。

**修复**：分支3 移出的牌优先来自"超过其 `suit_min`"的花色（`protected = {s for s,n in suit_min.items() if vdist[s] <= n}`），无多余花色时才退而移出会破坏约束的牌。

**验证**：逆叫16+ 50% → 100%，技术性加倍 76% → 88%。基准 `bench_mh.py` 覆盖 8 种真实约束模式，确认 `beta=1.0` 最优。

---

## 5. 改动文件清单

| 文件 | 改动 |
|------|------|
| `bridge/mcts/direct_dds.py` | `_load_dll()` 调 `SetMaxThreads(cpu_count)`；`_dll_lock` 保护所有求解调用 |
| `bridge/mcts/sampler.py` | 新增 `_check_feasible` / `_constraint_violation_score` / `_pick_least_violating`；`_sample_one` 接入预检与兜底保护；`_sample_uniform` 重写保证世界完整；`_propose_swap` 补花色移出最高 HCP 非目标牌；`_position_hcp_feasible` 合并 exact_suit |
| `bridge/mcts/dd_search.py` | `endgame_card_threshold` 默认值对齐为 4；采样传均匀模式 |
| `dbg_repro.py`（新增） | 诊断脚本：复现 void 回填失败场景，验证采样世界完整性与 DDS 求解成功率 |

---

## 6. 项目记忆同步

以下结论已写入 `project_memory.md`：
- DealSampler 只允许均匀采样；定向/偏置采样明确禁止。
- 定向采样不可行（取牌顺序偏见 + 历史废弃先例）。
- 性能"下降"是 DDS 缓存假象，非 bug。
- DD/αμ 样本生成代码一致，仅评估方式不同。
- `_sample_uniform` 必须保证世界完整（每张牌都分配、绝不丢牌），void 由上层验证链剔除而非采样时丢牌。
- `_propose_swap` 补花色移出最高 HCP 非目标牌，避免 HCP 升高被 Metropolis 接受率拒绝。
- 中局采样慢（54s/924 世界仅 16 有效）根因是采样生成不完整世界被 DDS 拒绝，而非 DDS 求解本身。