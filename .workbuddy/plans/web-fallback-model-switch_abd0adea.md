---
name: web-fallback-model-switch
overview: 为网页版添加备用AI模型切换功能，让用户可以在设置面板中选择使用 DeepSeek Chat 或 DeepSeek Reasoner 作为备用模型
design:
  architecture:
    framework: react
    component: mui
  styleKeywords:
    - Material Design
    - 简洁
    - 一致性
  fontSystem:
    fontFamily: PingFang SC
    heading:
      size: 1.25rem
      weight: 500
    subheading:
      size: 1rem
      weight: 400
    body:
      size: 0.875rem
      weight: 400
  colorSystem:
    primary:
      - "#1976d2"
    background:
      - "#ffffff"
      - "#f5f5f5"
    text:
      - "#333333"
      - "#666666"
    functional:
      - "#4caf50"
      - "#f44336"
todos:
  - id: add-backend-api
    content: 在 api/main.py 添加备用模型获取和设置接口
    status: completed
  - id: add-frontend-api
    content: 在 web/src/services/api.js 添加备用模型API调用函数
    status: completed
  - id: add-frontend-state
    content: 在 App.jsx 添加备用模型状态管理和设置面板UI
    status: completed
    dependencies:
      - add-frontend-api
  - id: integrate-bid-call
    content: 修改 aiBid 调用，传递备用模型参数
    status: completed
    dependencies:
      - add-frontend-state
---

## 产品概述

为网页版桥牌叫牌练习系统添加备用AI模型切换功能，允许用户在设置面板中手动选择备用提示词使用的AI模型（deepseek-chat 或 deepseek-reasoner）。

## 核心功能

- 在网页版设置面板中添加"备用AI模型"下拉选择框
- 后端提供获取当前备用模型和设置备用模型的API接口
- 前端将用户选择的模型持久化到localStorage
- 叫牌请求时传递备用模型参数给后端

## 技术栈

- 前端：React + Material-UI (MUI)
- 后端：FastAPI (Python)
- 状态管理：React useState + localStorage

## 实现方案

### 后端修改 (api/main.py)

1. 添加 Pydantic 模型 `FallbackModelRequest` 和 `FallbackModelResponse`
2. 添加 GET `/api/fallback-model` 接口：返回当前配置的备用模型
3. 添加 POST `/api/fallback-model` 接口：更新备用模型配置
4. 修改 POST `/api/bid` 接口：支持接收 `fallback_model` 参数

### 前端修改 (web/src/services/api.js)

1. 添加 `getFallbackModel()` 函数：调用 GET /api/fallback-model
2. 添加 `setFallbackModel(model)` 函数：调用 POST /api/fallback-model
3. 修改 `aiBid()` 函数：添加 `fallbackModel` 参数

### 前端修改 (web/src/App.jsx)

1. 添加状态 `fallbackModel`，从 localStorage 初始化
2. 在设置面板中添加"备用AI模型"下拉选择框（位于"发牌设置"区域下方）
3. 添加 `handleFallbackModelChange` 处理函数，更新状态并同步到后端和localStorage
4. 修改 `handleAIBid` 调用，传递 `fallbackModel` 参数

## 架构设计

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   前端 (React)   │────▶│  FastAPI 后端    │────▶│ DeepSeekClient  │
│                 │     │                 │     │                 │
│ - 设置面板下拉框  │     │ - GET/POST 接口  │     │ - fallback_model│
│ - localStorage  │◀────│ - 模型配置管理   │◀────│ - 动态切换      │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

## 目录结构

```
web/src/
├── App.jsx              # [MODIFY] 添加备用模型状态和下拉框
└── services/
    └── api.js           # [MODIFY] 添加备用模型API调用

api/
└── main.py              # [MODIFY] 添加备用模型管理接口
```

在现有设置面板中添加一个简洁的"AI模型设置"区域，包含备用AI模型的下拉选择框。设计遵循现有UI风格，使用Material-UI组件保持一致性。

### 设置面板布局

在"发牌设置"区域下方新增"AI模型设置"区域，包含：

- 标题：AI模型设置
- 下拉框：备用AI模型（选项：DeepSeek Chat / DeepSeek Reasoner）
- 说明文字：简要解释两个模型的区别

### 样式

- 使用与现有设置项相同的FormControl和Select组件
- 下拉框宽度：minWidth: 200px
- 与上方"发牌设置"区域用Divider分隔