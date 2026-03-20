# 桥牌叫牌练习系统

一个基于 AI 的桥牌叫牌练习工具，支持双人/四人叫牌练习，使用 JF 叫牌约定，通过 DeepSeek API 实现 AI 叫牌决策。

## 功能特点

- 🃏 **双人/四人叫牌模式** - 支持不同位置的叫牌练习
- 🤖 **AI 叫牌决策** - 基于 DeepSeek 大模型
- 📖 **JF 约定支持** - 内置 JF 叫牌约定知识库
- 🖼️ **图片识别** - 支持从截图识别牌局
- 📊 **Deep Finesse 集成** - 定约可行性分析
- 📱 **响应式界面** - 支持桌面和移动端

## 安装

### 环境要求

- Python 3.8+
- Node.js 18+ (用于前端)

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
   
   编辑 `.env` 文件，填入您的 API 密钥：
   ```
   DEEPSEEK_API_KEY=your_deepseek_api_key_here
   ```

5. **运行程序**
   ```bash
   python run.py
   ```

## 使用说明

### 叫牌模式

| 模式 | 说明 |
|------|------|
| 双人叫牌 | 南北方向或东西方向叫牌 |
| 四人叫牌 | 四家位置轮流叫牌 |

### 输出格式

- **图形化输出** - 牌桌布局，包含手牌显示和叫牌表格
- **紧凑输出** - 四行布局（南西北东顺序）
- **Deep Finesse 格式** - 用于 Deep Finesse 分析

### 主要功能

1. **发牌** - 随机生成一副牌
2. **输入牌局** - 手动输入特定牌局
3. **图片读牌** - 从图片文件识别牌局
4. **Deep Finesse 分析** - 分析定约可行性
5. **历史记录** - 管理叫牌历史

## 获取 API 密钥

1. 访问 [DeepSeek 官网](https://platform.deepseek.com/)
2. 注册账号并登录
3. 在 API Keys 页面创建新的 API 密钥

## 项目结构

```
bridge-bidding-system/
├── main.py              # 主程序入口
├── config.py            # 配置文件
├── requirements.txt     # Python 依赖
├── api/                 # API 接口
├── bridge/              # 桥牌逻辑
├── knowledge/           # 知识库加载
├── llm/                 # LLM 调用
├── utils/               # 工具函数
├── web/                 # 前端代码
│   ├── src/             # React 组件
│   ├── public/          # 静态资源
│   └── package.json     # 前端依赖
└── .env.example         # 环境变量模板
```

## 技术栈

- **后端**: Python, FastAPI
- **前端**: React, Material-UI, Vite
- **AI**: DeepSeek API

## 常见问题

**Q: 提示"API 密钥无效"怎么办？**

A: 请检查 `.env` 文件中的 API 密钥是否正确，确保没有多余的空格或引号。

**Q: 如何查看 AI 的叫牌分析过程？**

A: 在设置中开启"显示完整 LLM 输出"选项。

## 许可证

本软件仅供学习和研究使用。
