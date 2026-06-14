# 桥牌叫牌练习系统 - 开发文档

## 项目概述

本项目是一个桥牌叫牌练习工具，从Dify工作流转换为独立应用。支持双人/四人叫牌练习，使用JF叫牌约定，通过DeepSeek API实现AI叫牌决策，集成Deep Finesse进行定约可行性分析。v1.32起新增打牌练习功能，支持AI打牌决策和双明手分析。v1.33全面重写打牌提示词，增强已见牌张追踪、防守信号体系和庄家分析框架。v1.37叫牌操作按钮迁移至叫牌详情面板，记录类型枚举重构。v1.39新增截屏/图片识别导入牌局（Doubao Vision API）、定约/首攻确认对话框、研究模式、花色主题感知系统。

## 功能模块

### 1. 发牌模块 (`bridge/dealer.py`)
- 自动生成随机牌局
- 计算每手牌的HCP（大牌点）
- 计算花色分布（S-H-D-C格式）
- 支持手动输入牌局
- 南北方向开叫概率 >70%

### 2. 叫牌模块 (`bridge/bidding.py`)
- 双人叫牌模式（南北或东西方向）
- 四人叫牌模式（四家位置）
- 人类参与叫牌功能
- 叫牌序列解析和管理
- 连续三家pass结束叫牌
- **叫牌序列关键字提取**（v1.6优化）：
  - `is_pair_bidding` 判断：检查所有偶数位置是否都是pass
  - 双人叫牌时始终返回 `first-third`（不限制长度）
  - 与双人和四人模式无关，与庄家位置无关
- **开叫位置关键字选择**（v1.29新增）：
  - 根据阻击叫牌体系选择开叫关键字
  - 自然阻击体系 → `花色开叫`
  - 多功能/麦德伯格体系 → `花色开叫1`（专用JF约定片段）
- **1NT开叫后对方争叫关键字提取**（v1.12新增）：
  - 根据`deal_system`配置区分对方争叫类型（自然阻击 vs 多功能/麦德伯格）
  - 细化关键字提取逻辑，精确匹配JF约定章节12.3.x系列
  - 支持应叫被干扰场景（我方开叫1NT后，应叫被对方X或争叫干扰）
  - 关键字映射：
    - X + 自然阻击 → `12.3`（12.3.1 加倍示强）
    - X + 多功能/麦德伯格 → `12.3.2\t 对方加倍表示别的含义`
    - 2C/2NT → `12.3.5\t 对方非自然争叫`
    - 2D/2H/2S + 自然阻击 → `12.3.4\t Rubensohl 约定叫`
    - 2D/2H/2S + 多功能/麦德伯格 → `12.3.5\t 对方非自然争叫`
    - ≥3阶 → `12.3.6\t 对方高阶争叫`
    - 应叫被干扰 → `12.3.3\t Stayman/转移叫被干扰`
- **1C/1D开叫后对方干扰关键字提取**（v1.13新增）：
  - len(bids)==2场景：区分对方加倍、一阶争叫、二阶争叫、高阶争叫
  - len(bids)==4场景：区分低花反加叫被干扰、开叫人的再叫
  - 关键字映射：
    - 对方加倍 → `12.1.1 对方加倍后`
    - 对方一阶争叫 → `对方一阶争叫`
    - 对方二阶争叫 → `对方二阶争叫：`（注意冒号）
    - 对方高阶争叫 → `我方开叫1低花`
    - 低花反加叫被干扰 → `低花反加叫被干扰`（序列：1C-(P)-2C-(争叫) 或 1D-(P)-2D-(争叫)）
    - 开叫人的再叫 → `开叫人的再叫`（第二家或第四家至少有一家争叫）

### 3. 叫牌服务模块 (`bridge/bidding_service.py`)
- AI叫牌决策服务
- `ai_bid()`: AI叫牌主方法，使用主提示词或备用提示词
- `_fallback_bid()`: 备用提示词叫牌方法
- `human_bid()`: 人类叫牌方法，获取叫品含义
- **阻击叫牌体系参数传递**（v1.29新增）：
  - 所有方法都接收并传递 `deal_system` 参数到提示词
  - 返回结果包含"阻击叫体系"字段

### 4. Deep Finesse模块 (`bridge/deep_finesse.py`)
- 定约可行性分析
- 支持当前牌局分析
- 支持直接输入Deep Finesse格式牌局
- 自动处理不同庄家位置
- 首攻牌张验证
- **缺门处理**（v1.5修复）：正确处理缺门花色，使用"-"占位符

### 5. 知识库模块 (`knowledge/loader.py`)
- JF约定文档加载（docx格式）
- 父子分段解析（按连续两个空行分段）
- 关键词检索（提取每个片段前三行作为关键词）
- **叫品结构预处理**（v1.8重写）：
  - `extract_bids_from_sequence()`: 从叫牌序列提取叫品列表
  - `extract_first_level_bids()`: 提取第一层所有叫品
  - `extract_first_level_bids_excluding_opening()`: 提取第一层叫品（排除开叫叫品）
  - `extract_response_bids()`: 提取应叫叫品列表
  - `find_partner_bid_in_tree()`: 在树状结构中定位队友叫品
  - `extract_subsequent_bids()`: 提取后续叫品（区分关键字行和树节点行）
  - `preprocess_jf_content()`: 整合预处理流程，返回结构化结果
  - `retrieve_with_preprocess()`: 检索并预处理的组合方法
- **树结构转换功能**（v1.9新增）：
  - `parse_content_to_tree()`: 将约定片段转换为树结构
  - 支持双叫品关键词（如1D-1H、1C-1D、2D-2NT）
  - 支持第三四家开叫1高花（如第三四家开叫1H、第三四家开叫1S）
  - 自动识别根节点并构建嵌套树结构
  - 双叫品关键词：根节点为第一个叫品，子节点为第二个叫品
  - 第三四家开叫：根节点为开叫品（1H或1S）
  - 多叫品拆解：识别包含"/"的叫品行，自动拆解成多个并列叫品
  - 单个字母叫品（C、D、H、S）自动推断为3阶叫品
- **树结构导航功能**（v1.9新增）：
  - `navigate_tree_by_bids()`: 根据叫牌序列在树结构中导航到目标节点
  - 自动处理根节点（跳过开叫品）
  - 支持双叫品关键词和第三四家开叫的导航
- **四种结构性约定片段处理**（v1.8重写）：
  - 花色开叫：无序列时提取开叫叫品；有序列时提取应叫叫品
  - 开叫后第一应叫：提取应叫叫品列表
  - 开叫-应叫后续：在树中定位队友叫品，提取直接后续
  - 第三四家1高花：序列≤1时提取应叫叫品；序列>1时定位队友叫品提取后续
- **后续叫品提取逻辑**（v1.8修复）：
  - 区分关键字行（如`1NT-2C`）和树节点行（如`├3S`）
  - 关键字行：后续叫品是缩进0的分支
  - 树节点行：后续叫品是缩进+1的子节点
- **预处理结果为空时自动切换**（v1.6新增）：
  - 当预处理结果为空时，自动尝试"成局与满贯"关键字
  - 充分利用JF约定中实际提供的约定长度
- **结构性约定判断简化**（v1.12新增）：
  - `is_structural_convention()` 函数只判断三种类型：
    - 开叫关键字（如 `1H开叫`、`1NT`、`2C`）
    - 双叫品关键字（如 `1D-1H`、`1C-1D`）
    - 第三四家开叫1高花（如 `第三四家开叫1H`）
  - 其他情况（包括 `12.3.x` 章节号关键字）均为非结构性约定
  - 移除 `has_structure` 参数，用 `len(subsequent_bids) > 0` 替代

### 6. LLM模块 (`llm/`)
- DeepSeek API集成（叫牌决策）
- 豆包视觉API集成（图片读牌、截屏识别）
- 主提示词/备用提示词切换机制
- **提示词规则加强**（v1.5）：
  - 主提示词AI权限限制：预处理和队友建议都为空时必须输出"JF无合格叫品"
  - 禁止暴露实际信息：只能引用约定范围，禁止暴露实际点力、张数、牌型

### 7. 历史记录模块 (`utils/history.py`)
- 保存叫牌记录
- 查看、删除、加载历史牌局
- 编辑备注

### 8. 截屏模块 (`utils/screenshot.py`)
- Edge浏览器窗口截屏
- 全屏截屏
- 豆包API识别牌局信息

### 9. 输出格式模块 (`bridge/output_format.py`) - v1.4新增
- 程序化生成三种输出格式，无需AI调用
- `generate_graphic_output()`: 图形化牌桌布局，包含手牌显示和叫牌表格
- `generate_compact_output()`: 紧凑型四行布局（南西北东顺序）
- `generate_deep_finesse_output()`: Deep Finesse格式，自动判断定约和庄家
- `determine_contract_and_declarer()`: 根据叫牌序列判断最终定约和庄家位置
- 支持双人叫牌模式的简化显示

### 10. 叫牌含义管理（v1.5新增）
- 双人模式：只保留最后一个叫牌的后续建议
- 四人模式：保留两个队伍各自的后续建议（南北队和东西队分别保留）
- 叫牌含义显示：在图形化布局和紧凑型布局之间显示，自动删除标签使输出简洁

### 11. 打牌模块 (`bridge/play_types.py`, `bridge/play_engine.py`, `bridge/play_service.py`) - v1.32新增
- **数据类型** (`play_types.py`):
  - `Card`: 牌张（花色+点数），支持从字符串解析
  - `Trick`: 一墩牌，记录4家出牌、AI标记、理由、风险
  - `PlayState`: 打牌状态（手牌、墩数、当前轮次、庄家/明手等）
  - `PlayPhase`: 打牌阶段（LEAD/PLAY/COMPLETE）
  - `PlayerRole`: 玩家角色（HUMAN/AI）
- **打牌引擎** (`play_engine.py`):
  - `PlayEngine.get_playable_cards()`: 获取当前可出牌张（含跟花色规则）
  - `PlayEngine.play_card()`: 执行出牌，自动判断墩赢家、归档完成的墩
  - `PlayEngine.get_visible_hands()`: 根据玩家角色返回可见手牌
  - `PlayEngine.is_complete()`: 判断打牌是否结束（13墩完成或手牌出完）
- **打牌服务** (`play_service.py`):
  - `PlayService.get_ai_play()`: AI打牌决策，调用LLM分析可出牌张
  - `PlayService.play_card()`: 出牌入口，支持人类和AI出牌
  - `PlayService.get_state_dict()`: 获取完整打牌状态（含墩赢家、可出牌等）
  - **打牌提示词增强**（v1.33新增）：
    - `_format_played_cards_info(state)`: 按花色统计已出/未见牌张，生成逐花色摘要
    - `_check_trump_cleared(state)`: 检查将牌是否已清完（区分庄家方/防守方剩余将牌）
    - `_format_defense_signals(state, current_player)`: 返回防守信号体系约定文本
- **API端点** (`api/main.py`):
  - `POST /api/play/start`: 开始打牌（传入定约信息）
  - `POST /api/play/card`: 人类出牌
  - `POST /api/play/ai-play`: AI出牌
  - `GET /api/play/state`: 获取打牌状态
  - `GET /api/play/playable`: 获取可出牌张
- **前端组件**:
  - `PlayPanel.jsx`: 打牌面板（出牌控制、墩数显示、AI分析）
  - `PlayTable.jsx`: 打牌桌面（4家手牌显示、当前墩出牌）
  - `PlayDetailPanel.jsx`: 打牌详情（已完成墩、AI出牌理由）

### 11.1 打牌交互流程 — 前端状态机设计

**状态变量**（App.jsx）:
| 变量 | 含义 | 触发时机 |
|------|------|----------|
| `playState` | 后端返回的完整打牌状态 | API调用后 set |
| `playInitiated` | 打牌已启动 | 点击"开始"按钮 或 重新打牌AI首攻 |
| `playStarted` | 第一张牌已打出 | `handlePlayCard` / `handleAIPlay` 成功后 |
| `isPlayPaused` | 暂停中 | 人类回合（墩中）/ 墩完成 / 手动暂停 / 墩首人类→AI切换 |
| `positionRoles` | 前端角色配置 `{位置: 'ai'|'human'}` | 角色切换Toggle触发 |

**核心逻辑函数**:

1. **`isCurrentPlayerHuman()`**（App.jsx:1564）:
   - 从 `positionRoles` 即时计算（非后端 `playState.is_human_turn`）
   - 当前玩家=明手时，读取庄家角色（桥牌规则：庄家替明手出牌）

2. **AI自动出牌**（App.jsx:1574-1589）:
   ```
   条件: showPlayPanel && playState && !playAiLoading && !playLoading && !isPlayPaused && playInitiated
   行为: 非人类回合 && 未完成 → 延迟500ms调用 handleAIPlay()
   依赖: [playState?.is_human_turn, playState?.phase, showPlayPanel, playAiLoading, playLoading, isPlayPaused, playInitiated, positionRoles]
   ```

3. **人类回合自动暂停**（App.jsx:1591-1599）:
   ```
   条件: showPlayPanel && playState && !playAiLoading && !playLoading && playInitiated
   行为: 人类回合 && 未完成 && 未暂停 && 非墩首 → setIsPlayPaused(true)
   注意: 墩首跳过，由"继续"按钮控制节奏
   ```

4. **墩完成检测**（App.jsx:1601-1623）:
   ```
   条件: showPlayPanel && playState
   行为: tricks.length增加 → 保存lastCompletedTrick → setIsPlayPaused(true)
        phase === 'complete' && tricks < 13 → saveCompletePlayRecord()
   ```

**角色切换逻辑** `handlePositionRoleChange`（App.jsx:1670-1729）:
- **庄家/明手双向同步**: 切换任一方→另一方同步更新（桥牌规则：庄家替明手出牌）
- **墩首人类→AI切换**: 自动暂停，显示"继续"按钮，点击后AI自动出牌
- **前端即时生效**: `setPositionRoles` 立即更新 → `isCurrentPlayerHuman()` 立即反映新角色
- **后端异步同步**: `updatePlayPlayerRoles(newRoles)` → 更新 `playState.player_roles`

**Toggle禁用条件**（CardTable.jsx:603）:
```
disabled = showPlayPanel && playInitiated
           && (!isPlayPaused || aiLoading)
           && !(isStartOfTrick && !aiLoading)

可切换场景:
- !playInitiated: 打牌尚未开始
- isPlayPaused && !aiLoading: 暂停中且AI空闲
- isStartOfTrick && !aiLoading: 每墩开头且AI空闲

不可切换场景:
- playInitiated && !isPlayPaused: AI自动出牌中（含暂停按钮可见时）
- aiLoading: AI正在思考
```

**按钮显隐规则**（PlayDetailPanel.jsx:487-545）:
| 按钮 | 显示条件 | 禁用条件 |
|------|----------|----------|
| 开始 | `!isComplete && !playInitiated` | — |
| 继续 | `!isComplete && playInitiated && isPaused && (!isHumanTurn \|\| isStartOfTrick)` | `aiLoading \|\| loading` |
| 暂停 | `!isComplete && playInitiated && !isPaused && !isHumanTurn` | — |
| 撤销 | `(!isComplete && playStarted && isPaused) \|\| (isComplete && !isHistoryRecord)` | `aiLoading \|\| loading` |

**选牌面板显隐**（PlayDetailPanel.jsx:226-246）:
```
1. isComplete → "打牌已结束"占位
2. !playInitiated || (isPaused && isStartOfTrick) → 隐藏（等待"开始"/"继续"）
3. isPaused && !isHumanTurn → 隐藏（AI回合暂停）
4. !isHumanTurn → 隐藏（AI思考中）
5. 否则 → 显示选牌面板
```

**每墩生命周期**:

```
墩首 (current_trick.cards.length === 0)
├─ 显示"继续"按钮（即使领出者是人类）
├─ 隐藏选牌面板
├─ 角色Toggle可切换
├─ 点击"继续":
│  ├─ 人类领出者 → 显示选牌面板（不暂停）
│  └─ AI领出者 → 自动出牌
└─ 人类→AI切换: 自动暂停，重新显示"继续"

墩中 (1 ≤ cards.length ≤ 3)
├─ 人类回合 → 自动暂停 + 选牌面板
├─ AI回合 → 自动出牌（可手动暂停）
├─ 暂停中角色Toggle可切换
└─ 点击"暂停" → 显示"继续" + "撤销"

墩完成 (cards.length === 4)
├─ 自动暂停，保存lastCompletedTrick
├─ 显示"继续" + "撤销"
└─ 第13墩完成 → phase='complete' → 自动保存记录
```

### 11.2 打牌提示词系统 - v1.33重大修改
- **提示词全面重写** (`llm/prompts.py` - `PLAY_SYSTEM_PROMPT`):
  - 新增8个模板变量：`bidding_sequence`、`trick_number`、`side`、`declarer_remaining`、`defender_remaining`、`trump_cleared`、`defense_signals_section`、`played_cards_info`
  - 信息区增强：
    - "已见牌张与花色轮次"：按♠♥♦♣逐花色列出已出/未见牌张
    - "防守信号体系约定"：条件区，仅防守方出牌时提供（姿态信号、张数信号、花色选择信号、首攻约定）
    - "得墩进度"：新增庄家/防守方剩余所需墩数
    - "将牌已清完"：帮助AI判断是否需要清将
  - 分析框架增强：
    - 庄家7步分析逻辑：赢墩计算→输墩计算→读防守→时效性→联通与进手→安全打法→终局打法
    - "推理过程"从隐含改为必须显式输出
  - 输出格式升级（8个字段）：
    - `推理过程`：从已见牌张推断剩余大牌位置，比较不同打法路线
    - `立场分析`：庄家视角 或 防守视角
    - `推荐出牌`：牌张代码
    - `核心逻辑`：一句话总结
    - `备选方案`：数组类型，列出备选牌张
    - `备选逻辑差异`：备选牌张与推荐牌张的差异
    - `风险提示`：具体风险描述
    - `后续路线建议`：下一轮或下一墩计划
- **输出Schema** (`llm/deepseek_client.py` - `PLAY_SCHEMA`):
  - 必填：`推理过程`、`立场分析`、`推荐出牌`、`核心逻辑`
  - 可选：`备选方案`（数组）、`备选逻辑差异`、`风险提示`、`后续路线建议`

### 12. 前端共享常量 (`web/src/constants/suits.js`) - v1.32新增
- `SUIT_SYMBOLS`: 花色符号映射（spades→♠等）
- `SUIT_COLORS`: 花色颜色映射（按花色名，red/black）
- `SUIT_COLOR_MAP`: 花色颜色映射（按符号字符）
- `getSuitColor()`: 辅助函数，统一花色颜色获取逻辑

### 13. 系统模式与位置角色 (`web/src/utils/position.js`) - v1.38新增

**核心概念**:
全部模式统一为一个维度：**positionRoles** — 每个位置是 AI 还是人类。

```javascript
// positionRoles 数据结构
{ '南': 'ai'|'human', '北': 'ai'|'human', '东': 'ai'|'human', '西': 'ai'|'human' }
```

一个位置是"练习"还是"模拟"，仅取决于该位置**有没有手牌**：
- 有手牌 → 练习模式（看到手牌，自己做决策）
- 无手牌 → 模拟实战（看到"未知"，手动输入实战中发生的叫品/出牌，AI 位置自动决策）

**工具函数**:
- `isHumanPosition(roles, pos)`: 判断某位置是否为人类
- `hasAnyHuman(roles)`: 判断是否有人类参与
- `getHumanPositions(roles)`: 获取所有人类位置列表
- `getPartnerPosition(pos)`: 获取对面位置（南↔北，东↔西）

**四人叫牌合法状态**:
| 状态 | Human | AI | 说明 |
|------|-------|----|------|
| 全 AI 旁观 | 0 | 4 | 发牌默认，自动叫牌+打牌 |
| 单人练习 | 1 | 3 | 人类参与叫牌/打牌 |
| 模拟实战 | 3 | 1 | 1个 AI 位置有手牌给建议，3个人类手动输入 |
| 全手动 | 4 | 0 | 所有位置手动输入 |

2H+2AI 被自动修正（不允许 2-2 分）：
- 1H+3AI 点另一 AI→人类：切换人类位置（新位置=human，其余=AI）
- 3H+1AI 点人类→AI：切换 AI 位置（原 AI→human，点击位→AI）

**双人叫牌方向**:
- 方向由发牌人位置自动推断：南/北→NS，东/西→EW
- 对手方在 `addBid` 中自动 pass
- 双人模式无打牌阶段（"切换到打牌"按钮隐藏）

**手牌可见性规则** (`CardTable.shouldShowHandContent`):

叫牌阶段：
- 全 AI → 显示所有手牌
- 1H+3AI 练习 → 人类手牌始终可见，AI 手牌受"队友手牌"/"对方手牌"checkbox 控制
- 3H+1AI 模拟实战 → AI 手牌始终显示，人类无手牌显示"未知"
- 4H 全手动 → 所有位置显示"未知"

打牌阶段：
- 明手始终可见
- 庄家受"庄家手牌"checkbox 控制
- 人类位置始终可见自己的手牌
- AI 无手牌位置显示输入框，Human 无手牌位置显示"未知"

**Checkbox 规则**:
| 阶段 | Checkbox | 显示条件 |
|------|----------|---------|
| 叫牌 | 队友手牌 | 1H+3AI 练习模式 |
| 叫牌 | 对方手牌 | 1H+3AI 练习模式 |
| 打牌 | 庄家手牌 | 庄家是 AI |
| 打牌 | 显示已出 | 始终显示 |

**涉及文件**:
- `web/src/utils/position.js` — 位置工具函数
- `web/src/App.jsx` — positionRoles 状态管理、位置切换约束、模拟实战按钮
- `web/src/components/CardTable.jsx` — shouldShowHandContent 统一手牌可见性
- `web/src/components/CardTablePanel.jsx` — checkbox 统一渲染
- `web/src/components/BiddingDetailPanel.jsx` — 双人模式隐藏打牌按钮
- `web/src/components/BiddingControls.jsx` — 使用 positionRoles
- `web/src/components/SettingsPanel.jsx` — 移除练习方向选择器

## 文件结构

```
Bidding System/
├── main.py                 # 主程序入口
├── config.py               # 配置管理
├── run.py                  # 运行入口
├── endplay_integration.py  # endplay双明手分析集成
├── .env                    # 环境变量（API密钥等）
├── .env.example            # 环境变量模板
├── requirements.txt        # Python依赖
├── build.spec              # PyInstaller配置
├── build.bat               # 打包脚本
├── update_release.ps1      # 更新发布包脚本
├── update_release.bat      # 更新发布包入口
├── installer.iss           # Inno Setup安装脚本
├── README.txt              # 用户手册
├── LICENSE.txt             # 许可协议
├── bridge/
│   ├── dealer.py           # 发牌和手牌管理
│   ├── bidding.py          # 叫牌序列解析
│   ├── bidding_service.py  # 叫牌服务（AI/人类叫牌）
│   ├── deep_finesse.py     # Deep Finesse集成
│   ├── output_format.py    # 输出格式生成
│   ├── play_types.py       # 打牌数据类型（v1.32新增）
│   ├── play_engine.py      # 打牌引擎（v1.32新增）
│   └── play_service.py     # 打牌服务（v1.32新增）
├── knowledge/
│   └── loader.py           # JF约定加载和检索
├── llm/
│   ├── prompts.py          # 提示词定义
│   ├── deepseek_client.py  # DeepSeek客户端
│   └── doubao_client.py    # 豆包视觉客户端
├── utils/
│   ├── history.py          # 历史记录管理
│   └── screenshot.py       # 截屏功能
├── api/
│   └── main.py             # FastAPI后端（叫牌+打牌API）
├── web/
│   └── src/
│       ├── App.jsx         # 主应用组件
│       ├── components/
│       │   ├── CardTable.jsx      # 牌桌（含打牌桌面）
│       │   ├── PlayPanel.jsx      # 打牌面板（v1.32新增）
│       │   ├── PlayTable.jsx      # 打牌桌面（v1.32新增）
│       │   ├── PlayDetailPanel.jsx # 打牌详情（v1.32新增）
│       │   ├── BiddingControls.jsx # 叫牌控制
│       │   ├── BiddingTable.jsx   # 叫牌过程表
│       │   ├── BiddingDetailPanel.jsx # 叫牌详情
│       │   ├── DoubleDummyTable.jsx # 双明手分析表
│       │   ├── ControlButtons.jsx  # 公共控制按钮
│       │   └── SettingsPanel.jsx   # 设置面板
│       ├── hooks/                 # 自定义Hooks
│       ├── constants/
│       │   └── suits.js           # 花色共享常量（v1.32新增）
│       ├── styles/
│       │   └── constants.js       # 样式常量
│       └── services/
│           └── api.js             # API服务层
├── screenshots/            # 截屏保存目录
├── bidding_history.json    # 历史记录存储
├── release_桥牌叫牌练习/    # 发布包目录
└── JF实战_标准自然 - Rev 3.2.docx  # JF约定文档
```

## 配置说明

### 环境变量 (.env)

```env
# DeepSeek API配置
DEEPSEEK_API_KEY=your_deepseek_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com

# 豆包（火山引擎）API配置
DOUBAO_API_KEY=your_doubao_api_key
DOUBAO_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
DOUBAO_VISION_ENDPOINT=your_vision_endpoint_id
```

### 获取API密钥

1. **DeepSeek**: https://platform.deepseek.com/
2. **豆包视觉**: 
   - 登录 https://console.volcengine.com/ark
   - 创建推理接入点，选择视觉模型
   - 复制接入点ID作为 `DOUBAO_VISION_ENDPOINT`

## 提示词系统

### 预处理结果注入（v1.4新增）
在检索JF约定后，系统自动进行叫品结构预处理：
1. 解析叫牌序列，定位队友最近叫品
2. 在文档内容中找到该叫品的行索引
3. 提取缩进级别+1的后续叫品列表
4. 将后续叫品列表注入提示词的 `{subsequent_bids}` 占位符

预处理结果示例：
```
【预处理提取的后续叫品】
队友北家最近叫品：1D
后续叫品列表（缩进深度+1）：
  - │-----├ 1H：4张H，6-10点
  - │-----├ 1S：4张S，6-10点
  - │-----├ 1NT：6-10点，没有四张高花
  - │-----├ 2C：10+点，4+C
```

### 主提示词 (BIDDING_SYSTEM_PROMPT)
- **用途**: 在JF约定中搜索匹配叫品
- **输出字段**: 12个
- **触发条件**: 默认使用
- **无合格叫品时**: 输出"JF无合格叫品"

### 备用提示词 (BIDDING_FALLBACK_PROMPT)
- **用途**: JF约定没有覆盖时的智能决策
- **输出字段**: 19个（增加配合花色、牌型点、进局判断等）
- **触发条件**: 主提示词输出"JF无合格叫品"后自动切换
- **特点**: 总是返回有效叫品

### 叫品选择优先级规则
- 开叫位置：优先选择无将（1NT/2NT）
- 非开叫和争叫位置：阶数相同时，高花>无将>低花
  - 例如：1S和1NT都是1阶，必须选择1S
  - 例如：2H和2NT都是2阶，必须选择2H

### 输出格式提示词 (OUTPUT_FORMAT_PROMPT)
生成三种格式的输出：
1. **图形化布局**: 矩形牌桌、手牌显示、叫牌过程表格
2. **紧凑型布局**: 南西北东顺序的四行手牌
3. **Deep Finesse格式**: Deal、Contract、OnLead、Lead信息

## 使用方法

### 启动程序
```bash
python main.py
```

### 主菜单选项
```
1. 发牌/输入牌局
2. 设置
3. 显示当前牌局
4. 开始叫牌
5. 分析定约可行性（Deep Finesse）
6. 查看历史记录
0. 退出
```

### 发牌/输入牌局子菜单
```
1. 自动发牌
2. 输入自定义牌局
3. 从图片读取牌局
4. 从Edge浏览器截屏
0. 返回
```

### 设置子菜单
```
1. 叫牌模式（双人/四人）
2. 庄家位置
3. 人类叫牌位置
4. 二阶开叫方案
5. LLM输出详细模式
6. 最终输出格式
0. 返回
```

## 输入格式

### 标准格式（按南西北东顺序）
```
K85 AT863 Q42 63
J73 72 8763 T954
QT94 5 KJT AQJ72
A62 KQJ94 A95 K8
```

### Deep Finesse格式
```
Deal: 1                                - AK865 K76 KJ962
Contract: 5D-South     QT9754 94 95 A53                  AKJ3 QJ732 T4 T7
OnLead: East                    862 T AQJ832 Q84
Lead: SA
```

## 牌张校验

从图片识别或截屏识别的牌局会自动校验：
- 牌张总数（应为52张）
- 各花色牌张数（应为13张）
- 重复牌张检测

校验错误时会显示警告信息。

## 打包发布

### 打包流程

1. **快速打包**：
   ```bash
   双击 build.bat
   ```

2. **更新发布包**：
   ```bash
   双击 update_release.bat
   ```

3. **创建安装程序**：
   - 安装 [Inno Setup](https://jrsoftware.org/isinfo.php)
   - 用 Inno Setup 打开 `installer.iss`
   - 编译生成安装程序

### 发布包内容

```
release_桥牌叫牌练习/
├── 桥牌叫牌练习.exe           # 主程序
├── JF实战_标准自然 - Rev 3.2.docx  # 约定文档
├── .env.example              # API配置模板
├── README.txt                # 使用说明
├── LICENSE.txt               # 许可协议
└── Deep Finesse 2014 v2/     # 分析工具
```

### 用户使用步骤

1. 复制 `.env.example` 为 `.env`
2. 填入 DeepSeek API 密钥
3. 运行 `桥牌叫牌练习.exe`

## 历史记录功能

### 保存记录
叫牌结束后询问是否保存，可添加备注。

### 查看历史记录
- 显示记录列表（时间、定约、模式、叫牌序列摘要）
- 查看详细信息
- 删除单条记录（d+编号）
- 加载历史牌局（l+编号）
- 编辑备注
- 清空所有记录

## Deep Finesse分析

### 分析当前牌局
在叫牌结束后或加载牌局后，选择菜单5进行分析。

### 直接输入分析
支持直接输入Deep Finesse格式的牌局进行分析，无需先叫牌。

### 输出格式
生成 `Last Hand.txt` 文件供Deep Finesse读取，包含：
- Deal: 牌局布局
- Contract: 定约和庄家
- OnLead: 首攻方
- Lead: 首攻牌张

## 叫牌结束条件

| 模式 | 结束条件 |
|------|----------|
| 双人叫牌 | 连续三家pass（包括不参与叫牌的两家） |
| 四人叫牌 | 连续三家pass |

## 依赖项

```
openai
python-dotenv
python-docx
pyautogui
pyscreeze
pillow
```

安装：
```bash
pip install openai python-dotenv python-docx pyautogui pyscreeze pillow
```

## 版本历史

### v1.38 (当前版本)
- **DeepSeek V4 非思考模式显式禁用修复**
  - 根因：DeepSeek V4 thinking 默认为 `enabled`，非思考模式下不传参数等价于开启思考
  - `chat()` 和 `chat_json()` 增加 `extra_body={"thinking": {"type": "disabled"}}` 显式关闭
  - 效果：叫牌 14-19s（原 60-90s），打牌 6-9s（原 30-78s），提速 3-5 倍
  - 修改文件: `llm/deepseek_client.py`
- **逼局进程强制规则（提示词修复）**
  - 备用提示词"叫品筛选过程"C段新增强制规则：逼局进程中禁止选择不逼叫的示弱叫品（简单重叫自己花色、简单加叫队友最低花色、pass）
  - 必须选择逼叫性叫品：跳叫新花 > 第四花色逼局 > 扣叫 > 2NT(逼叫) > 其他强制逼局约定叫品
  - 案例记录：case-033（北家14点AKQJT7，1C-X-1H-P-2C后应选2D人工逼局）
  - 修改文件: `llm/prompts.py`, `bidding-cases/2026-05-01/case-033.json`, `bidding-cases/cases-index.json`
- **叫牌细节面板布局重构**
  - 记录下拉框移至按钮行左端，与"开始/暂停/撤销/保存/切换到打牌"同行
  - "切换到打牌"从内容区独立行合并到按钮行右端
  - "简单"checkbox右对齐到标题栏，简单模式下记录下拉框置灰禁用
  - 内容区滚动条从外层移至内层内容容器，按钮行固定不滚动
  - 修改文件: `web/src/components/BiddingDetailPanel.jsx`
- **AI提供商选择器移除**
  - SettingsPanel、App.jsx、useGameSettings、api.js全面移除DeepSeek/Doubao切换
  - 修改文件: `web/src/components/SettingsPanel.jsx`, `web/src/App.jsx`, `web/src/hooks/useGameSettings.js`, `web/src/services/api.js`
- **叫牌控制面板暗色背景适配**
  - `getBidColor` 增加 `isDark` 参数，暗色下所有按钮统一黑灰背景(`#1e293b`)白色文字(`#e2e8f0`)
  - 主面板、JF面板、定约结果卡片背景暗色适配
  - 修改文件: `web/src/components/BiddingControls.jsx`
- **系统标题与按钮栏合并**
  - 桌面版和手机版"桥牌练习系统"标题与ControlButtons合并到同一行
  - 修改文件: `web/src/App.jsx`
- **加载历史记录出牌失败修复**
  - 从历史记录加载打牌时，先调 `playInit` 初始化后端，再重放已有出牌使后端状态与记录一致
  - 修改文件: `web/src/App.jsx`
- **打牌详情面板输入模式滚动条修复**
  - 输入模式外层容器设 `overflow: 'hidden'`，仅保留提示词框滚动条
  - 修改文件: `web/src/components/PlayDetailPanel.jsx`

### v1.37
- **叫牌操作按钮迁移至BiddingDetailPanel**
  - 开始叫牌/重新叫牌、暂停/继续、撤销、保存按钮从顶部ControlButtons移至BiddingDetailPanel按钮行
  - 按钮右对齐，与打牌面板布局一致
  - 暂停按钮加 `disabled={stopBidding && aiThinking}`：暂停后切换为"继续"，AI未返回时禁用
  - 叫牌进行中时开始/重新叫牌按钮隐藏；叫牌暂停时只显示"继续"按钮
- **已保存未完成牌局加载后"继续"按钮修复**
  - 打牌详情面板"继续"按钮条件增加 `isHistoryRecord`，从历史加载时不受回合限制
  - 修复人类回合保存再加载后无法继续的问题
- **加载完整叫牌记录后重新叫牌不自动开始**
  - `resetBidding` 移除 `startBidding()` 调用，改为显示"开始"按钮等待用户点击
  - 发牌人是人类时点击"开始"自动显示叫牌控制面板
- **humanPosition 与 positionRoles 同步修复**
  - 新增 `useEffect` 监听 `positionRoles` 自动同步到 `humanPosition`
  - `loadRecordToTable` 恢复 `positionRoles` 状态
  - 移除 `handlePositionRoleChange` 中的重复同步
- **记录类型枚举重构**
  - 4种保存类型：`bidding_in_progress`（叫牌进行中）、`bidding_complete`（仅叫牌完成）、`play_in_progress`（打牌进行中）、`play_complete`（打牌完成）
  - 历史记录面板标签更新，精确反映各记录状态
  - 修改文件: `web/src/App.jsx`, `web/src/components/PlayDetailPanel.jsx`, `web/src/components/BiddingDetailPanel.jsx`, `web/src/components/ControlButtons.jsx`

### v1.36
- **修复主提示词pass叫品误触发fallback**
  - `_is_no_valid_bid`方法：当`bid="pass"`时直接返回`False`，不再检查筛选过程中的"无合格叫品"关键词
  - 主提示词约定无合格叫品输出`"JF无合格叫品"`，pass是合法叫品时输出`"pass"`，两者不应混淆
  - 修复前：LLM选择pass时，若筛选过程描述中含"无合格叫品"措辞，会误切换到备用提示词，JF约定从"花色开叫"变为"成局与满贯"
  - 修复后：pass作为合法叫品直接返回，不再误触发fallback
  - 添加verbose模式调试日志，记录关键字提取、预处理结果和决策路径
  - 修改文件: `bridge/bidding_service.py`

### v1.35
- **暗色模式全面适配**
  - 所有前端组件硬编码颜色替换为 `theme.palette.mode === 'dark'` 条件分支
  - 手牌面板（HandDisplay）、牌桌面板（CardTablePanel）、叫牌细节面板（BiddingDetailPanel）、打牌详情面板（PlayDetailPanel）暗色适配
  - 双明手表格（DoubleDummyTable）暗色适配，统一"-"与定约方块样式
  - 牌桌中心出牌区域空位/卡片/hover暗色适配
  - 打牌选择卡片选中/可选/不可选三态暗色适配
  - 墩数统计面板（庄家方/防守方/需要）暗色适配
  - 绿色牌桌背景暗色调整（`#2e7d32→#1b5e20` → `#1a3a1c→#0d1f0f`）
  - 清除手牌按钮暗色适配
  - 主题切换开关从SettingsPanel移至顶部ControlButtons最右端图标按钮
  - 修改文件: 12个前端文件 + App.css + App.jsx

### v1.34
- **将牌将吃Bug修复**（关键修复）
  - 修复 `Contract.from_str()` 花色代码与 `Card.suit` 不匹配：英文代码（S/H/D/C）转换为中文符号（♠/♥/♦/♣）
  - 修复前将牌将吃永远不会被识别为赢墩，将牌相关逻辑全部失效
- **有将/无将坐庄策略分离** (`llm/prompts.py`)
  - "赢墩与输墩分析"分为两种模式：有将定约数输墩（5步评估清单）、无将定约数赢墩（5问规划）
  - "全局规划"输出字段同步分为有将/无将两种内容模板
- **全局规划字段前端显示** (`PlayDetailPanel.jsx`)
  - 新增"全局规划"字段显示（青色，多行），"后续路线建议"改为多行显示
- **打牌按钮交互重构**
  - 叫牌面板"开始打牌"→"切换到打牌"，点击后只切换状态不自动开始
  - 打牌面板新增开始/暂停/继续三态按钮，第一张牌打出后显示暂停
  - 重新打牌按钮移到开始/暂停/继续旁边，右对齐，统一outlined风格
  - 打牌结束后隐藏开始/暂停/继续，只保留重新打牌
  - 新增 `playInitiated` 状态区分"已点击开始"和"已出第一张牌"
  - 重新打牌后不再切回叫牌界面，AI首攻自动开始，人类首攻等待出牌
- **人类出牌交互优化**
  - 取消"出牌"确认按钮
  - 第一次点击选中，再次点击确认出牌

### v1.33 (当前版本)
- **打牌提示词重大修改**
  - 全面重写 `PLAY_SYSTEM_PROMPT`，新增8个模板变量
  - 新增"已见牌张与花色轮次"信息区，帮助AI推断剩余大牌位置
  - 新增"防守信号体系约定"条件区（仅防守方出牌时提供）
  - 新增"庄家分析逻辑"7步框架
  - "推理过程"从隐含改为必须显式输出
  - 输出格式升级为8个字段（推理过程、立场分析、推荐出牌、核心逻辑、备选方案、备选逻辑差异、风险提示、后续路线建议）
  - 更新 `PLAY_SCHEMA` 适配新字段
  - 新增3个辅助方法：`_format_played_cards_info`、`_check_trump_cleared`、`_format_defense_signals`
- **打牌提示词准确性加强**（v1.33a）
  - 新增"连张vs间张"概念澄清：KJ不是连张，AQ不是连张；连张要求大牌相邻（如KQJ、QJT）
  - 首攻示例增加反例：KJ75长四首攻（非01首攻）、AQ754长四首攻
  - 首攻表格注释加强：攻J前提是J10相邻，KJ后面没有10时不适用攻J规则
  - 新增"出牌位置策略"规则：明确四家出牌不同策略，第四家不存在后续出牌者
  - 新增"本墩出牌位置"信息：第X家（已有X张牌，你之后还有X家未出牌）
  - 第二、三家防守方策略统一指向"首攻与信号"部分，避免规则重复矛盾
  - 信号定义加强：信号仅适用于跟牌，领出时不存在信号
  - 已完成墩格式增加领出者标注：`第1墩[领出:南]`
  - 当前墩格式增加领出者标注：`[领出:南] (南)♠5 (西)♠2`
  - 空墩提示增加领出说明：`尚未开始（你是本墩领出者）`
- **前端：移除重复的叫牌记录管理逻辑**
  - App.jsx 使用 `useBiddingState` 和 `useBiddingRecords` hook 替代内联状态管理
  - 删除约170行重复代码
  - Hook 函数重命名避免命名冲突：`initBiddingState`、`markBiddingStarted`、`toggleStopBiddingState`
  - `isBiddingComplete` 逻辑同步为完整版本（支持3连续pass检测）
- **打牌阶段UI优化**
  - 右侧记录下拉框切换时面板位置不再跳动
  - 左右面板顶部栏高度统一为40px
  - 左侧标题颜色与右侧统一
  - 打牌状态下墩数标签移入白色面板
  - 四家手牌与中间面板间距优化
  - 牌桌中心文字和旋转控件优化

### v1.32
- **打牌模块代码清理与优化**
  - 移除后端4个文件中约16处DEBUG print语句
  - 修复 `play_types.py` 中死代码：移除NT/非NT重复分支、未使用的 `_get_right_hand()` 方法、`get_visible_hands()` 无效的 pass 分支
  - 修复 `play_card` API 端点 `trick_complete` 判断 bug（原判断永远为 False）
  - 提取 API 重复代码为辅助函数：`_format_bidding_sequence()`、`_parse_vision_hands()`、`_hands_to_response_dict()`
  - 将 `import re/traceback/tempfile/os` 移到 `api/main.py` 文件顶部，消除约15处内联 import
  - 新增前端共享常量 `web/src/constants/suits.js`，3个组件改为 import 共享常量
  - 提取 `CardTable.jsx` 中重复的 `renderCenterContent()` 函数，合并桌面版和手机版30+行重复渲染代码

### v1.31
- **前端代码结构优化**
  - 提取5个自定义 Hooks：`useBiddingRecords`、`useGameSettings`、`useBiddingState`、`useDoubleDummy`、`useOutputFormats`
  - 提取 `SettingsPanel` 组件，减少约57行代码
  - 创建统一样式常量文件 `constants.js`
  - 清理未使用的组件导入
- **手机版 JF 约定面板优化**
  - 固定高度显示（手机版 500px，网页版 400px）
  - 内容超出时显示滚动条
  - 叫牌控制按钮使用自适应 grid 布局，修复溢出问题

### v1.30
- **前端组件结构优化**
  - 提取 `ControlButtons` 公共组件，合并桌面版和手机版控制按钮
  - 清理 `App.css` 中未使用的样式
  - 共减少约250行冗余代码
- **删除手机版面板拖拽排序功能**
  - 删除 `MobileDraggableContainer` 组件
  - 删除 @dnd-kit 依赖
  - 简化手机版布局代码

### v1.29
- **阻击叫牌体系参数传递优化**
  - 三个提示词添加 `{deal_system}` 占位符，指导AI根据所选体系选择叫品
  - `bidding_service.py` 完善参数传递链路
  - 开叫位置关键字选择：根据体系选择"花色开叫"或"花色开叫1"
  - 输出显示添加"阻击叫体系"字段
- **发牌人调整逻辑优化**
  - 停止叫牌后可调整发牌人
  - 调整发牌人时重置叫牌状态（清空序列、重置按钮状态）
- **代码清理**
  - 删除 `explain_bid` 和 `build_bid_history` 方法（v1.27添加的叫牌建议功能残留）
  - 删除 `EXPLAIN_BID_PROMPT` 提示词

### v1.28
- **移除叫牌建议功能**
  - 移除"练习/建议"模式切换按钮
  - 删除 `BiddingSuggestion.jsx` 组件
  - 移除 `getBiddingSuggestion` API函数
  - 移除后端 `/api/bidding-suggestion` 端点
  - 保留练习模式和JF约定片段功能
- **发牌人设定功能重构**
  - 去掉顶部下拉框，改为点击方位标签设定
  - 使用"*"代替"(发)"作为发牌人标记
  - 叫牌过程中禁止修改发牌人
- **UI优化**
  - 叫牌细节标签的控制/细节切换位置固定
  - 当前牌局框切换改为"叫牌过程/小房子"
  - 字体加大，AI手牌checkbox移动到最右端
- **Bug修复**
  - **人类叫牌含义确定问题**（关键修复）：
    - 问题：用户叫3S，但显示pass的含义
    - 原因：`addBid` 使用旧的 `humanPosition` 状态，但系统已改用 `positionRoles`
    - 修复：判断逻辑改为 `positionRoles[currentBidder] === 'human'`
    - 同时修复 `human_bid` 方法返回值和 `fetchOutputFormats` 参数

### v1.27
- **叫牌建议功能**
  - 新增"建议"模式，与"练习"模式切换
  - 支持截屏识别手牌和叫牌序列
  - 双模式手牌输入（文本/点选花色）
  - 叫牌序列编辑（下拉选择叫品）
  - 发牌人自动从第一个叫品位置推断
  - 建议结果显示（默认叫品+可展开完整分析）
- **叫牌历史构建** (`bidding_service.py`)
  - `explain_bid()`: 解释叫品含义（优先JF约定匹配，否则AI解释）
  - `build_bid_history()`: 从叫牌序列构建叫牌历史
- **新增提示词** (`prompts.py`)
  - `EXPLAIN_BID_PROMPT`: 在不知道手牌的情况下解释叫品含义

### v1.26
- **历史记录删除确认逻辑**
  - 删除前检查选中记录是否包含注释
  - 有注释时弹出确认对话框，显示注释数量
  - 无注释时直接删除，无需确认
  - 防止误删有价值的注释记录

### v1.25
- **历史记录多选功能**
  - 每条记录前添加复选框，支持多选
  - 点击记录行即可选择/取消选择
  - 选中记录高亮显示
  - 全选/取消全选按钮
- **导出导入增强**
  - 导出时可选导出部分记录（选中时只导出选中的）
  - 导入支持多条记录合并，自动去重
  - 导出文件包含完整 `aiBiddingHistory` 数组
- **AI详细输出记录**
  - 每条记录保存AI叫牌的 `full_output`
  - 包含手牌分析、叫牌历史、叫品筛选过程
- **操作按钮统一**
  - 移除每条记录单独的按钮
  - 所有操作按钮集中在底部
- **截图功能改进**
  - 直接触发系统截图工具（Win+Shift+S）
  - 5秒延迟后自动读取剪贴板
- **FormData上传修复**
  - 移除多余的 `Content-Type` header
- **新增叫牌案例**
  - case-029：6-5双高套竞争叫牌
  - case-030：竞争叫牌中跳叫自己花色
- **新增Skill**
  - `bridge-bidding-recorder`：叫牌案例记录skill

### v1.24
- **双明手分析Bug修复**
  - 修复`endplay_integration.py`中`trump_order`顺序错误（应为S,H,D,C,NT）
  - 解决所有将牌数据错位问题，CLI和Web结果一致
- **备用模型切换功能**
  - 主提示词失败时自动切换到备用提示词
  - 备用提示词使用temp=0.5进行自然推理
- **启动脚本优化**
  - 添加`--reload`参数支持热重载
  - 修复uvicorn启动命令
- **备份系统完善**
  - 案例数据`bidding-cases/`加入Git跟踪（29个案例）
  - 更新`create-restore-point` skill备份范围
  - 创建本地恢复点`backup_20260326_225200/`
- **叫牌案例记录**
  - 新增case-028：东家4C扣叫错误案例
- **文档全面更新**
  - 使用`.trae/skills/update-changelog` skill更新CHANGELOG和DEVELOPMENT
  - 补充从v1.0到v1.24的完整版本历史

### v1.23
- **网页版双明手分析显示优化**
  - 创建`DoubleDummyTable.jsx`组件，使用与叫牌过程相同的表格格式
  - 将Checkbox改为Switch控件，更适合切换场景
  - 所有单元格统一使用浅蓝色背景
  - 移除HCP显示，只保留定约信息
  - 叫牌细节面板下拉框字体大小与标题一致
  - 历史记录加载后按钮显示"重新叫牌"，自动切换到显示叫牌过程
  - 每次切换显示时重新分析，确保结果与当前牌局同步

### v1.22
- **双明手分析功能集成（endplay）**
  - 新增`endplay_integration.py`模块，集成endplay库
  - 支持批量计算所有庄家-将牌组合的最高可完成定约
  - 主程序新增菜单选项"9. 批量双明手分析"
  - Hand类新增`to_simple_string()`方法支持空花色显示
  - 新增多个测试文件验证功能
  - **v1.24修复**：修正`trump_order`顺序为S,H,D,C,NT（与endplay的Denom枚举一致）

### v1.21
- **提示词与JF约定优化 - 满贯探查规则整合**
  - 成局定约定义明确：3NT/4H/4S为25点，5C/5D为28点，强调4C/4D不是成局定约
  - 关键张计算规则只保留纯粹计算逻辑，删除重复的答叫选择规则
  - 4NT问叫/答叫规则简化为一行引用JF约定
  - 扣叫控制规则精简，只保留防止幻觉规则和输出格式
  - JF约定更新：添加问叫资格检查、禁止pass停在答叫花色等规则
- **成局定约检查规则强化**
  - 在"选择最终叫品"步骤添加成局定约检查规则
  - 强调低花成局必须到5阶，防止LLM错误选择4C/4D作为成局定约

### v1.20
- **UI优化和进度指示器改进**
  - 修复选择人类玩家位置后白屏问题
  - 叫牌进度指示器移至手牌框右上角，添加半透明背景
  - 移除"界面设置"部分，配色功能代码保留
  - 手机版标题单独显示，控制按钮简化
  - 手机版叫品按钮增大（46x40px），方便点击

### v1.19
- **游戏管理系统**
  - 新建`bridge/game_manager.py`，创建`BiddingGameManager`单例类和`BiddingGame`类
  - 支持UUID游戏ID，便于多用户并发
  - 终端和网页共享核心叫牌逻辑
- **API端点重构**
  - 新增游戏管理API：create、state、deal、bid、formats
  - 修复AI叫牌422错误（bid字段改为可选）
  - 修复发牌速度慢问题（移除重复发牌调用）
- **JF约定片段和预处理逻辑修复**
  - 检索关键词、JF约定片段和预处理结果一起传给LLM
  - 两种情况转备用提示词：预处理为空、主提示词无合格叫品
- **主提示词失败输出显示**
  - 网页版显示主提示词选择合格叫品失败的输出
- **手机适配**
  - 响应式设计，叫牌控制面板100%宽度
  - 牌桌布局手机上垂直排列
- **设置面板重构**
  - "游戏设置"改名为"叫牌设置"
  - 新增"发牌设置"组，四种发牌模式
- **叫牌控制面板激活逻辑修复**
  - 任何位置设为人类玩家时都激活
- **搭档相继pass逻辑修复**
  - 只在第一个实质性叫牌后触发
  - 修复bug：找搭档pass时排除第一个实质性叫牌之前的pass
  - 场景 `(东)pass-(南)1D-(西)pass-(北)1H-(东)?` 不再错误触发自动pass
- **主动保存进度功能**
  - 叫牌进行中可手动点击"保存"按钮保存进度
  - 记录类型统一：`in_progress`（进行中）、`complete`（完成）
  - 通过 `sourceRecordId` 关联同一牌局的多次保存
  - 重新叫牌/重新打牌不重置记录关联，继续覆盖同一记录
  - 新发牌时创建新记录
- **Deep Finesse格式庄家修复**
  - 移除重复格式转换
- **远程访问配置**
  - 支持`0.0.0.0`绑定

### v1.19
- **桌面版布局优化**
  - 修复重复JF约定片段面板问题
  - 调整牌桌尺寸：宽度700px，高度750px
  - 对齐"当前牌局"和"叫牌细节"面板标题高度
  - 关闭叫牌细节后，叫牌控制和JF约定面板移至右侧垂直排列
  - 叫品按钮重排：每行10个叫品，紧凑布局
  - 7阶叫品与1、3、5阶对齐，X/XX/Pass与2、4、6阶对齐
  - 添加分割线分隔按钮和面板区域
- **手机版修复**
  - 删除重复"更多格式"面板
- **项目清理**
  - 删除tests目录40个调试临时文件
  - 保留30个正式测试文件
  - 删除根目录临时文件
  - 更新.gitignore
- **Git版本控制初始化**
  - 创建 `.gitignore` 文件，排除敏感文件和构建产物
  - 首次提交：`Initial commit: 桥牌叫牌练习系统 v1.8.2`
- **GitHub远程仓库配置**
  - 仓库地址：`https://github.com/fangoner/bridge-bidding-system`
  - API密钥安全：`.env` 已被忽略，不会泄露
- **项目文档完善**
  - 添加 `README.md`：项目介绍、安装步骤、使用说明、项目结构
  - 添加 `.env.example`：环境变量配置模板

### v1.18
- **检验定约功能**
  - 新增`/api/analyze-contract`接口，调用Deep Finesse分析定约
  - 前端新增"检验定约"按钮（在更多格式框标题栏）
  - 点击后自动启动Deep Finesse并置顶窗口
  - 使用`EnumWindows`和`GetWindowThreadProcessId`查找窗口并置顶
- **术语修正**
  - 将"庄家"改为"发牌人"（第一个叫牌的人）
  - 保留"庄家"用于最终定约显示（定约方中第一个叫出该花色的人）
  - 修改提示词中"第一家（庄家）"为"第一家（发牌人）"
- **Deep Finesse格式优化**
  - 第一行：Deal: 1 后22个空格
  - 第二行：东西手牌之间4个空格
  - 第三行：West 后17个空格
  - 确保在500px宽度内正常显示
- **UI改进**
  - "发牌"按钮改为"重新发牌"（已有牌局时）
  - 更多格式框宽度改为500px
  - 叫牌结束时自动隐藏JF约定片段框
  - 加载历史记录时避免重复保存（使用`useRef`）
- **终端程序自动pass叫牌含义**
  - 自动pass时添加叫牌含义："搭档已相继pass，不再参与叫牌"

### v1.17
- **紧凑格式和Deep Finesse格式显示修复**
  - 修复API中Position枚举重复定义导致的500错误
  - 加载历史牌局后自动获取并显示更多格式
  - 更多格式框宽度调整为430px
- **终端程序搭档相继pass后自动pass功能**
  - 新增`passed_partnership`属性记录已相继pass的搭档
  - 新增`check_partner_consecutive_pass`函数检测搭档是否相继pass
  - 新增`is_in_passed_partnership`函数检查位置是否属于已pass的搭档
  - 四人叫牌模式下，搭档两人相继pass后，后续自动pass

### v1.16
- **Web版叫牌历史累积功能修复**
  - 网页版叫牌历史格式与终端版保持一致：`\n(位置)叫品含义`
  - 每次叫牌后累积叫品含义，形成完整的叫牌历史
  - 修改提示词中"叫牌历史"字段描述
- **叫牌结束后添加"重新叫牌"按钮**
  - 叫牌结束界面新增"重新叫牌"按钮
  - 保持当前牌局，重新开始叫牌流程
- **四人叫牌模式AI调用优化**
  - 搭档两人相继pass后，这两人在后续叫牌中直接pass（不调用AI）
  - pass仍加入叫牌序列和叫牌历史，避免分析错误
  - 另一方两人正常调用AI叫牌
- **Vite配置固定端口**
  - 添加 `strictPort: true` 配置，固定前端端口为5173

### v1.15
- **Web版JF约定片段显示优化**
  - 用户点击"显示JF约定片段"checkbox时，根据当前叫牌序列获取JF约定片段
  - 没有相关约定时显示"JF尚未提供建议"
  - 取消勾选时清空显示内容
- **JF约定片段框布局调整**
  - 水平方向和LLM输出框右端对齐
  - 固定最大高度300px，与叫牌控制框高度一致
  - 内容区域使用overflow: auto实现滚动条
- **叫牌逻辑优化**
  - 发牌后biddingStarted设置为false，需要等待开始
  - 观察模式：需要点击"开始叫牌"按钮，AI全程自动叫牌
  - 人类参与但不是第一个叫牌：需要点击"开始叫牌"按钮
  - 人类第一个叫牌：发牌后等待人类叫牌，人类叫牌后AI继续

### v1.14
- **Web版桥牌叫牌练习系统全面完善**
  - 添加"开始叫牌"按钮，AI叫牌流程匹配终端版本
  - LLM输出框响应式设计，支持历史记录查看
  - API超时增加到120秒，启用LAN访问
  - 修复庄家识别逻辑（第一个叫该花色的人）
  - 自动记录叫牌结果，支持查看、编辑、删除
  - JF约定片段功能，只在人类叫牌时显示
  - 修复双人叫牌流程，对方阵营自动pass正确显示

### v1.13
- **1高花开叫后对方干扰关键字提取优化**
  - len(bids)==2场景：区分对方加倍、双套争叫、普通争叫
  - len(bids)==4场景：区分再加倍、简单加叫后敌方参与
  - 关键字映射：
    - 对方加倍 → `12.2.1 敌方加倍`
    - 确定双套争叫(2NT) → `对抗对方已明确的 55 双套争叫：`
    - 已知一套双套争叫(2H/2S) → `对抗对方只已知一套的 55 双套争叫：`
    - 普通争叫 → `12.2.2 敌方争叫花色`
    - 再加倍 → `12.2.4 关于再加倍`
    - 简单加叫后敌方参与 → `12.2.3 我方简单加叫后敌方参与`
- **1低花开叫后双套争叫关键字提取优化**
  - 1C-2C：对方双高花55双套争叫
  - 1C-2NT：对方5H+5D双套争叫
  - 1D-2D：对方双高花55双套争叫
  - 1D-2NT：对方5H+5C双套争叫
  - 均使用关键字 `对抗对方已明确的 55 双套争叫：`
- **跳扣叫关键字提取**
  - 敌方1阶开叫后，我方3阶跳扣叫同一花色表示问挡张
  - 序列 `(1X)-3X-(pass/争叫)-?` 返回关键字"跳扣叫"

### v1.13
- **1C/1D开叫后对方干扰关键字提取优化**
  - 细化关键字提取逻辑，精确匹配JF约定章节
  - len(bids)==2场景：区分对方加倍、一阶争叫、二阶争叫、高阶争叫
  - len(bids)==4场景：区分低花反加叫被干扰、开叫人的再叫
- **关键字映射表**:
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

### v1.12
- **1NT开叫后对方争叫关键字提取优化**
  - 根据`deal_system`配置区分对方争叫类型（自然阻击 vs 多功能/麦德伯格）
  - 细化关键字提取逻辑，精确匹配JF约定章节12.3.x系列
  - 新增应叫被干扰场景的关键字提取（12.3.3）
  - 支持两种二阶开叫方案的关键字区分
  - 关键字使用精确匹配，直接使用章节标题（含制表符）
- **关键字映射表**:
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

### v1.11
- **打包发布功能**
  - PyInstaller打包配置（`build.spec`）
  - 一键打包脚本（`build.bat`、`update_release.ps1`）
  - Inno Setup安装程序配置（`installer.iss`）
  - 发布文档（`README.txt`、`LICENSE.txt`、`.env.example`）
  - 发布包结构：EXE + 约定文档 + 配置模板 + Deep Finesse
- **历史记录管理界面优化**
  - 操作结果显示位置调整：记录清单后面、菜单前面
  - 重构 `view_history` 函数显示流程
- **LLM幻觉问题修复**
  - 扣叫控制判断增加防幻觉规则
  - 要求必须引用实际持牌作为判断依据
  - 禁止编造手牌中没有的牌张

### v1.10
- **叫品提取逻辑修复**
  - 修复 `extract_response_bids` 函数：同时检查中文冒号"："和英文冒号":"
  - 解决预处理结果中缺少3NT叫品的问题
  - 预处理结果从26个增加到28个
- **检索逻辑修复**
  - 修复 `retrieve` 函数：移除模糊匹配逻辑，只保留精确匹配
  - 解决"1NT-3NT"错误匹配到"1NT开叫"的问题
  - 当找不到精确匹配的关键词时，返回空内容

### v1.9
- **树结构转换和多叫品拆解功能**
  - 新增 `parse_content_to_tree()` 函数：将约定片段转换为树结构
  - 支持双叫品关键词（如1D-1H、1C-1D、2D-2NT）
  - 支持第三四家开叫1高花（如第三四家开叫1H、第三四家开叫1S）
  - 自动识别根节点并构建嵌套树结构
  - 双叫品关键词：根节点为第一个叫品，子节点为第二个叫品
  - 第三四家开叫：根节点为开叫品（1H或1S）
  - 多叫品拆解：识别包含"/"的叫品行，自动拆解成多个并列叫品
  - 单个字母叫品（C、D、H、S）自动推断为3阶叫品
  - 所有拆解的叫品共享相同的描述
- **树结构导航功能**
  - 新增 `navigate_tree_by_bids()` 函数：根据叫牌序列在树结构中导航到目标节点
  - 自动处理根节点（跳过开叫品）
  - 支持双叫品关键词和第三四家开叫的导航
- **预处理逻辑更新**
  - 双叫品关键词：使用树结构导航提取队友叫品和后续叫品
  - 第三四家开叫：使用树结构导航提取队友叫品和后续叫品
  - 自动设置正确的start_idx（跳过开叫品）
- **测试覆盖**
  - 1D-1H：所有测试序列正常工作
  - 1C-1D：所有测试序列正常工作
  - 2D-2NT：所有测试序列正常工作
  - 第三四家开叫1H：所有测试序列正常工作
  - 第三四家开叫1S：所有测试序列正常工作
  - 多叫品拆解："2S/3C/D/H"→"2S"、"3C"、"3D"、"3H"
  - 多叫品拆解："3C/D/H/S"→"3C"、"3D"、"3H"、"3S"
  - 多叫品拆解："3S/4C"→"3S"、"4C"

### v1.8
- **预处理逻辑重写**
  - 重写 `preprocess_jf_content` 函数，根据四种结构性约定片段类型分别处理
  - 新增辅助函数：`extract_bids_from_sequence`、`extract_first_level_bids`、`extract_first_level_bids_excluding_opening`、`extract_response_bids`、`find_partner_bid_in_tree`
  - 修复 `extract_subsequent_bids` 函数：区分关键字行和树节点行
  - 关键字行（如`1NT-2C`）：后续叫品是缩进0的分支
  - 树节点行（如`├3S`）：后续叫品是缩进+1的子节点

### v1.7
- **移除后续建议功能**
  - 简化预处理逻辑，不再提取二级叫品
  - 更新所有提示词模板，删除"后续建议"和"队友建议"相关字段
  - 简化叫品筛选过程逻辑
- **备用提示词逻辑优化**
  - 从主提示词切换时不再使用预处理结果
  - 叫品筛选过程：从JF约定原文提取 → 自然约定
- **人类提示词逻辑优化**
  - 根据约定类型决定JF约定内容
  - 结构性约定使用预处理结果，描述性约定使用完整JF约定片段
- **结构性约定预处理为空时自动切换**
  - 结构性约定 + 预处理为空 → 备用提示词 + "成局与满贯"约定
  - 新增 `jf_keyword` 参数传递，确保显示正确的关键词
- **叫品递增规则加强说明**
  - 明确花色等级：**S > H > D > C**
  - 增加具体例子避免LLM误解

### v1.6
- **双人叫牌序列补全逻辑**
  - 新增 `_get_bidding_str_for_keyword()` 方法：在双人叫牌模式下自动补上下一个位置的pass
  - 修复 `ai_bid()` 被调用时序列还未补全的问题
- **代码重构**
  - 新增 `_format_subsequent_bids()` 方法：提取公共的后续叫品格式化逻辑
  - 消除 `ai_bid()` 和 `human_bid()` 中的重复代码
- **双人叫牌关键字提取优化**
  - 新增 `is_pair_bidding` 判断：检查所有偶数位置是否都是pass
  - 双人叫牌时始终返回 `first-third`（不限制长度）
  - 充分利用JF约定中实际提供的约定长度
- **预处理结果为空时自动切换**
  - 当预处理结果为空时，自动尝试"成局与满贯"关键字
- **四人叫牌与双人叫牌逻辑统一**
  - 四人叫牌中一方主叫、另一方不参与时，使用双人叫牌逻辑
  - 叫牌序列分析与模式设置无关，与庄家位置无关

### v1.5
- **Deep Finesse格式缺门处理修复**
  - 修复 `df_format_to_hand` 和 `hand_to_df_format` 函数
  - 缺门花色现在正确使用 "-" 占位，避免位置错乱
- **单叫品关键字预处理修复**
  - 修复"第三四家开叫1H"等单叫品关键字的后续叫品提取
  - 新增逻辑：当标题行没有叫品时，向下查找包含单个叫品的行作为关键字行
- **主提示词AI权限限制加强**
  - 加强"叫品筛选过程"和"叫品选择"字段的规则
  - 明确规定：预处理和队友建议都为空时，必须输出"JF无合格叫品"，不能自行决定叫品
- **禁止暴露实际信息规则加强**
  - 三个提示词都添加了 `**【禁止暴露实际信息】**` 标记
  - 明确禁止暴露实际点力、实际花色张数、具体牌型
- **bid_meanings后续建议处理优化**
  - 双人模式：只保留最后一个叫牌的后续建议
  - 四人模式：保留两个队伍各自的后续建议（南北队和东西队分别保留）
- **叫牌含义显示优化**
  - 在"全部格式"输出模式下，叫牌含义显示在图形化布局和紧凑型布局之间
  - 显示时删除"1. **叫品含义**："和"2. **后续建议**："等标签，使输出更简洁

### v1.4
- **重要变更：JF约定预处理功能**
  - 新增叫品结构预处理模块，在检索JF约定后自动提取后续叫品
  - 通过缩进级别解析（`│----`模式）准确识别叫品层级关系
  - 预处理结果直接注入提示词，避免AI误判后续叫品
  - 新增函数：`parse_indent_level()`、`extract_bid_from_line()`、`find_partner_bid_in_content()`、`extract_subsequent_bids()`、`preprocess_jf_content()`
  - 提示词新增 `{subsequent_bids}` 占位符，显示预处理提取的后续叫品列表
  - 简化"叫品筛选过程"指令，优先使用预处理结果
- **重要变更：输出格式程序化生成**
  - 新增 `bridge/output_format.py` 模块，程序化生成三种输出格式
  - 移除AI生成输出格式的调用，节省token和API成本
  - `generate_graphic_output()`: 图形化牌桌布局
  - `generate_compact_output()`: 紧凑型四行布局
  - `generate_deep_finesse_output()`: Deep Finesse格式
  - 自动判断定约和庄家位置
  - 无需API Key即可生成格式化输出

### v1.3
- 新增历史记录功能（保存、查看、加载、删除）
- 新增Edge浏览器截屏识别功能
- 新增牌张校验功能
- 修复叫品选择优先级问题（高花>无将>低花）
- 修复逼局状态判断问题（区分逼叫一轮和逼局）

### v1.2
- 集成Deep Finesse定约分析
- 支持Deep Finesse格式输入
- 支持不同庄家位置
- 首攻牌张验证

### v1.1
- 重构菜单结构
- 修复双人叫牌序列生成
- 修复叫牌结束逻辑
- 南北开叫概率调整

### v1.0
- 初始版本，从Dify工作流转换
- 实现发牌、双人/四人叫牌
- JF约定知识库检索
- DeepSeek API集成
- 三种输出格式
- 图片读牌功能
