# 项目规则

## 启动系统
当用户说"启动系统"或"启动"时，必须同时检查并启动前端和后端服务：
1. 先清理残留进程（node: vite, python: uvicorn）
2. 启动后端：`uvicorn api.main:app --host 0.0.0.0 --port 8003 --reload`
3. 启动前端：`npm run dev`（在 web/ 目录）
4. 确认两个服务都正常运行后告知用户

## 代码风格
- 不要添加注释
- 字符串用双引号
