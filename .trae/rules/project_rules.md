# 项目规则

## 启动系统

当用户说"启动系统"或"启动"时，必须同时检查并启动前端和后端服务：

1. 先清理残留进程（node: vite, python: uvicorn）
2. 启动后端：`uvicorn api.main:app --host 0.0.0.0 --port 8003`（不用 --reload，多文件连续编辑时易崩溃）
3. 启动前端（生产构建）：在 web/ 目录执行 `npm run build && npm run preview`（5173 端口不变，/api 经 preview 代理到 8003；dev 模式 + StrictMode 双重渲染是界面迟滞最大单一因素）
4. 确认两个服务都正常运行后告知用户

## 代码风格

- 不要添加注释

- 字符串用双引号

