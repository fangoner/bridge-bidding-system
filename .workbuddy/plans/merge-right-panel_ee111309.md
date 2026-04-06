---
name: merge-right-panel
overview: 合并桌面版和手机版右侧面板：叫牌控制+JF约定+叫牌细节，人类回合显示叫牌控制+JF约定，AI回合/叫牌结束切换到叫牌细节；按钮改为四行（每行两阶）。
todos:
  - id: modify-bidding-controls
    content: 修改 BiddingControls 组件，添加 hideJFPanel prop
    status: completed
  - id: refactor-app-desktop
    content: 重构 App.jsx 桌面版右侧面板逻辑
    status: completed
    dependencies:
      - modify-bidding-controls
  - id: test-bidding-flow
    content: 测试叫牌流程：人类回合、AI回合、叫牌结束各场景
    status: completed
    dependencies:
      - refactor-app-desktop
  - id: refactor-app-mobile
    content: 重构 App.jsx 手机端面板逻辑
    status: completed
    dependencies:
      - test-bidding-flow
  - id: update-changelog
    content: 更新 CHANGELOG 记录本次修改
    status: completed
    dependencies:
      - refactor-app-mobile
---

## 产品概述

重新设计并实现网页版桥牌叫牌练习系统的右侧面板布局，将叫牌控制、JF约定面板和叫牌细节合并为一个统一的面板。

## 核心功能

1. **统一右侧面板**：将叫牌控制、JF约定片段和叫牌细节整合到同一个右侧面板中
2. **智能切换逻辑**：

- 人类回合（humanPosition === currentBidder）：上部显示叫牌控制，下部显示JF约定片段
- AI回合（叫牌进行中，但不是人类回合）：**切换到叫牌细节面板**
- 叫牌结束：显示叫牌细节
- 观察者模式（无人类参与）：始终显示叫牌细节

3. **叫牌按钮布局优化**：四行排列，每行显示两阶叫品（1级+2级 / 3级+4级 / 5级+6级 / 7级+特殊）
4. **桌面版和手机版统一处理**：先完成桌面版，再同步修改手机端

## 详细需求

### 面板显示逻辑

| 场景 | 人类参与 | 叫牌状态 | 右侧面板显示内容 |
| --- | --- | --- | --- |
| 观察者模式 | 否 | 任意 | 叫牌细节（AI输出） |
| 人类参与 | 是 | 人类回合 | 上部：叫牌控制，下部：JF约定 |
| 人类参与 | 是 | AI回合 | 叫牌细节（查看AI叫牌过程） |
| 人类参与 | 是 | 已结束 | 叫牌细节（完整历史） |


### 布局要求

- 右侧面板总高度保持 750px
- 叫牌控制区域：固定高度约 280px（紧凑布局，四行按钮）
- JF约定区域：flex: 1，占剩余空间，overflow: auto
- 叫牌细节：占满整个 750px

### 交互细节

1. 人类回合时显示叫牌控制+JF约定
2. AI回合时自动切换到叫牌细节面板
3. 叫牌结束后自动切换到叫牌细节视图
4. 保留"简单显示"模式切换功能

## 技术栈

- **前端框架**：React 18
- **UI组件库**：Material-UI (MUI) v5
- **状态管理**：React useState/useEffect hooks
- **样式方案**：MUI sx props + CSS 文件

## 实现方案

### 1. 修改 BiddingControls 组件

添加 `hideJFPanel` prop，允许父组件控制是否渲染 JF约定面板：

```
function BiddingControls({
  // ... 现有 props
  hideJFPanel = false,  // 新增：控制是否隐藏JF约定面板
})
```

当 `hideJFPanel=true` 时，只渲染叫牌控制部分，不渲染 JF约定 Paper。

### 2. 重构 App.jsx 桌面版右侧面板逻辑

新的右侧面板结构（伪代码）：

```
<Paper height=750px>
  {humanPosition === null ? (
    // 观察者模式：始终显示叫牌细节
    <BiddingDetailsPanel />
  ) : isBiddingComplete() ? (
    // 人类参与且叫牌结束：显示叫牌细节
    <BiddingDetailsPanel />
  ) : isHumanTurn ? (
    // 人类参与且人类回合：上部叫牌控制 + 下部JF约定
    <Box display=flex flexDirection=column height=100%>
      <Box height=280px>  // 叫牌控制区域
        <BiddingControls hideJFPanel=true isVerticalLayout=true />
      </Box>
      <Box flex=1 overflow=auto>  // JF约定区域
        <JFSuggestionPanel />
      </Box>
    </Box>
  ) : (
    // 人类参与且AI回合：显示叫牌细节
    <BiddingDetailsPanel />
  )}
</Paper>
```

### 3. JF约定面板提取

将 JF约定片段的渲染逻辑从 BiddingControls 中提取，在 App.jsx 中直接内联渲染，便于控制布局。

### 4. 删除冗余代码

- 删除第 1808-1828 行的第二行 BiddingControls（原在叫牌细节下方）
- 删除 `showAIBiddingOutput` 相关的条件分支（第 1506-1805 行）

### 5. 保留设置面板中的开关

`showAIBiddingOutput` checkbox 保留，但修改其行为：

- 人类参与模式：该开关无效，始终使用新的合并面板
- 观察者模式：该开关控制是否显示叫牌细节（保持现有行为）

## 架构设计

```mermaid
graph TB
    subgraph Desktop["桌面版布局"]
        CT[CardTable<br/>700x750px]
        RP[右侧面板<br/>flex:1 x 750px]
    end
    
    subgraph RightPanel["右侧面板内容"]
        direction TB
        OBS[观察者模式<br/>叫牌细节]
        HUMAN_TURN[人类参与-人类回合<br/>上部: 叫牌控制<br/>下部: JF约定]
        AI_TURN[人类参与-AI回合<br/>叫牌细节]
        HUMAN_END[人类参与-已结束<br/>叫牌细节]
    end
    
    CT --> RP
    RP --> OBS
    RP --> HUMAN_TURN
    RP --> AI_TURN
    RP --> HUMAN_END
    
    style HUMAN_TURN fill:#e3f2fd
    style HUMAN_END fill:#f3e5f5
    style OBS fill:#fff3e0
    style AI_TURN fill:#e8f5e9
```

## 目录结构

```
d:/Bridge Card/Bidding System/web/src/
├── App.jsx                    # [MODIFY] 重构右侧面板逻辑
└── components/
    └── BiddingControls.jsx    # [MODIFY] 添加 hideJFPanel prop
```

## 关键实现细节

### 状态判断逻辑

```js
// 判断是否是人类回合
const isHumanTurn = humanPosition !== null && humanPosition === currentBidder;

// 判断是否显示叫牌控制 + JF约定
const showBiddingControlPanel = isHumanTurn && !isBiddingComplete();

// 判断是否显示叫牌细节（AI回合、叫牌结束、观察者模式）
const showBiddingDetailsPanel = !showBiddingControlPanel;
```

### 向后兼容处理

```js
// 观察者模式下，showAIBiddingOutput 仍然有效
if (humanPosition === null && !showAIBiddingOutput) {
  // 显示空的占位区域或简化提示
}
```

### 叫牌按钮布局

当前 `allBidsCompact` 已经是四行每行两阶（5+空+5）的布局，满足需求：

- 行1: 1级 + 2级
- 行2: 3级 + 4级  
- 行3: 5级 + 6级
- 行4: 7级 + 特殊叫品