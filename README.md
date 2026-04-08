# RRviewer
By Yizhou Han

AI 驱动的复习提要生成器（FastAPI + HTML/CSS/JS）。支持：
- 一次免登录试用（Cookie 控制）
- Google / Microsoft OAuth 登录
- 上传文件或粘贴文本，生成大纲 / Q&A / 闪卡
- 基于生成结果的小聊天窗（支持批量问答）

界面亮点：
- 统一工作台（`workspace.html`）：
  - 左侧“文件泡泡”盒子（支持 PDF/DOCX/TXT/CSV/XLSX）
  - 中部“大号生成区”，包含格式选择与提示词建议
  - 右侧“小聊天窗”，围绕最新生成内容进行问答
- 左上角 AI 状态指示（已连接 / 模拟 / 未配置）
- 中英文双语切换，主题色与动效优化

目录结构：
- `backend/` FastAPI 后端
- `frontend/` 静态前端页面
- `start.ps1` 一键启动脚本（Windows）
- `start.sh` 一键启动脚本（Ubuntu 22.04 / Linux）
- `docker-compose.yml` 本地容器编排

## 快速开始（Windows，本地运行）
推荐使用一键脚本：

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1 -Mode local
```

## 快速开始（Ubuntu 22.04，本地运行）
推荐使用一键脚本：

```bash
chmod +x ./start.sh
./start.sh --mode local
```

如需跳过依赖安装：

```bash
./start.sh --skip-deps
```

Docker 模式：

```bash
./start.sh --mode docker
```

启动后：
- 前端：http://localhost:8080/index.html（会自动跳转至 workspace）
- 后端：http://localhost:8000

## Docker 本地部署

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1 -Mode docker
```

或手动：

```powershell
docker compose up --build
```

前端 http://localhost:8080，后端 http://localhost:8000。

## 使用流程
1) 登录或试用：
	- 首次可点击“先试用一次”；或使用 Google/Microsoft 登录。
2) 上传/粘贴：
	- 点击“上传”选择本地文件；成功后会在左侧出现“文件泡泡”，并自动将解析文本填入生成输入框。
3) 生成：
	- 选择格式（大纲 / Q&A / 闪卡），完善提示（科目、范围、重点/难点），点击“生成”。
4) 聊天：
	- 在右侧小聊天窗提问，系统会基于当前生成结果作答；支持批量问答。

## 环境变量（backend/.env）
将 `backend/.env.example` 复制为 `backend/.env` 并填写：

| 变量 | 说明 | 示例 |
|---|---|---|
| APP_ENV | 环境名 | dev / prod |
| SECRET_KEY | JWT 签名密钥 | change-me |
| ALLOWED_ORIGINS | 允许的前端来源，逗号分隔 | http://localhost:8080,http://127.0.0.1:8080 |
| OPENAI_API_KEY | OpenAI API Key | sk-xxxx |
| DEEPSEEK_API_KEY | DeepSeek API Key | sk-xxxx |
| LLM_PROVIDER | LLM 提供商 | openai / deepseek / mock |
| LLM_MODEL | 模型名 | gpt-4o-mini / deepseek-chat |
| GOOGLE_CLIENT_ID | Google OAuth Client ID | ... |
| GOOGLE_CLIENT_SECRET | Google OAuth Client Secret | ... |
| MICROSOFT_CLIENT_ID | Microsoft OAuth Client ID | ... |
| MICROSOFT_CLIENT_SECRET | Microsoft OAuth Client Secret | ... |
| DATABASE_URL | 数据库 URL | sqlite:///./rrviewer.db |

说明：若未配置真实 API Key，将自动退化为 mock 模式以便本地开发；OAuth 在本地演示环境下会走简化流程并在回调页同步 Token。

## 端到端 CI（GitHub Actions）
仓库包含工作流：
- 单元测试：安装依赖并运行 `backend/tests`
- E2E：`docker compose up`，等待后端健康，调用关键端点做冒烟验证

## 故障排查
- API 连接问题：前端已内建 API 基址与超时处理（`frontend/src/pages/assets/api.js`）。若依然失败，请确认：
  - 后端是否运行在 8000 端口；
  - 浏览器地址与 `ALLOWED_ORIGINS` 是否匹配；
  - 控制台网络请求状态码与 CORS 报错信息。
- 试用策略：首次访问会设置 `rr_trial=active`，允许同会话多次请求；用尽后需登录。
- AI 未连接：检查 `LLM_PROVIDER` 与对应 API Key 是否设置；或在 mock 模式下继续使用。

## 开发提示
- 后端代码入口：`backend/app/main.py`
- 路由：`/auth`, `/upload`, `/generate`, `/chat`, `/status/ai`
- LLM 提供商：OpenAI、DeepSeek 或 mock（无外网时可用）
