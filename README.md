# catch_fish — 闲鱼商品获取与性价比分析系统

基于 **A2A (Agent-to-Agent) 协议** + **MCP (Model Context Protocol)** 的多智能体协作系统。用户通过自然语言描述需求，系统自动调度多个 AI Agent 协同工作：搜索闲鱼二手商品 → 获取新品百科资料 → 计算性价比 → 返回购买建议。

```
用户: "iPhone 15 Pro 256G 二手值得买吗？"
  ↓
系统: 闲鱼最低 ¥6,200（比新品便宜 30%），性价比评分 85，推荐购买 ✅
```

## 系统架构

```
用户终端 → A2A 网关 (FastAPI) → Orchestrator 调度器
                                      │
                   ┌──────────────────┼──────────────────┐
                   ▼                  ▼                  ▼
          ┌──────────────┐  ┌────────────────┐  ┌────────────────┐
          │ Finder Agent │  │Encyclopedia    │  │Calculator      │
          │  (闲鱼搜索)    │  │    Agent       │  │    Agent       │
          │              │  │  (商品百科)     │  │  (性价比分析)   │
          └──────┬───────┘  └──────┬─────────┘  └──────┬─────────┘
                 │                 │                    │
                 ▼                 ▼                    ▼
          ┌──────────────┐  ┌────────────────┐  ┌────────────────┐
          │ 闲鱼 MCP     │  │ LLM (DeepSeek)  │  │ 规则引擎+LLM   │
          │ Server       │  │ 训练数据提供     │  │ 综合评分       │
          │ (cookie登录)  │  │ 商品信息         │  │               │
          └──────────────┘  └────────────────┘  └────────────────┘

                  Chat Agent (多轮对话入口，SSE流式返回)
                       │
                       ├── 意图路由: 新搜索 / 追问 / 对比 / 详情 / 闲聊
                       └── 上下文管理: 会话Session + 搜索成果复用
```

运行模式：

| 模式 | 命令 | 说明 |
|------|------|------|
| **单进程模式** | `python -m src.main --standalone` | 所有 Agent 进程内直接调用，推荐本地开发 |
| **热重载模式** | `python -m src.main --standalone --reload` | 代码变动自动重启 |
| **A2A 分布式** | `python -m src.a2a.launcher` | 启动全部 Agent 微服务（端口 8001-8004），适合生产部署 |

## 技术栈

| 组件 | 技术 |
|------|------|
| 语言 | Python 3.11+ |
| Web 框架 | FastAPI + SSE (Server-Sent Events) |
| ASGI 服务器 | Uvicorn |
| AI Agent | 自研 Agent 框架 + DeepSeek API (OpenAI 备用) |
| LLM | DeepSeek (主) / GPT-4o (备用) |
| 协议 | A2A (JSON/HTTP) + MCP |
| 数据模型 | Pydantic v2 |
| 数据库 | MySQL 8.0 + SQLAlchemy (异步: aiomysql) |
| 缓存 | Redis 7 |
| HTTP 客户端 | httpx (异步) |
| 日志 | Loguru |
| 重试机制 | Tenacity |
| 部署 | Docker + Docker Compose |

## 快速开始

### 前置条件

- Python 3.11+
- Docker & Docker Compose（或本地 MySQL + Redis）
- DeepSeek API Key（可选，也支持 OpenAI）
- 闲鱼 Cookie（可选，用于真实搜索；不配置则使用 LLM 模拟数据）

### 安装

```bash
# 1. 克隆项目
git clone <your-repo-url> catch_fish
cd catch_fish

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入你的 DEEPSEEK_API_KEY
# 可选: 填入 XIANYU_COOKIE 启用真实闲鱼搜索

# 3. 安装依赖
pip install -r requirements.txt

# 4. 启动基础服务（MySQL + Redis）
docker compose up -d mysql redis

# 5. 启动应用（单进程模式）
python -m src.main --standalone

# 6. 访问 API 文档
# http://localhost:8000/docs
```

### 本地开发

```bash
# 开发模式（热重载）
python -m src.main --standalone --reload

# 运行测试
pytest tests/ -v
```

## API 接口

### 1. Chat API — SSE 流式多轮对话（推荐）

```bash
# 发起对话（SSE 流式返回）
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "iPhone 15 Pro 二手值得买吗"}'

# SSE 事件类型:
#   session   — 会话信息（session_id）
#   progress  — Agent 执行进度（stage + detail）
#   message   — AI 回复文本
#   result    — 搜索结果 JSON（触发搜索时）
#   error     — 错误信息
#   done      — 流结束标记

# 追问（传入 session_id 延续对话）
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "第一个怎么样", "session_id": "xxxx"}'
```

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/chat` | POST | SSE 流式多轮对话 |
| `/api/v1/chat/{session_id}/history` | GET | 获取会话历史 |
| `/api/v1/chat/{session_id}/summary` | GET | 会话摘要 |
| `/api/v1/chat/{session_id}` | DELETE | 结束会话 |
| `/api/v1/chat/sessions` | GET | 列出活跃会话 |

### 2. Search API — 异步搜索（传统方式）

```bash
# 发起搜索
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "iPhone 15 Pro 256G 国行 深空黑 二手值得买吗",
    "budget_min": 5000,
    "budget_max": 8000,
    "condition": "all"
  }'

# Response
{
  "search_id": "a1b2c3d4",
  "status": "accepted",
  "estimated_seconds": 30
}

# 查询进度
curl http://localhost:8000/api/v1/search/a1b2c3d4/status

# 获取结果
curl http://localhost:8000/api/v1/search/a1b2c3d4/result
```

### 3. 健康检查

```bash
curl http://localhost:8000/api/v1/health
# {"status": "ok", "version": "0.1.0", "service": "catch_fish"}
```

## 项目目录结构

```
catch_fish/
├── docker-compose.yml          # Docker 编排（MySQL + Redis）
├── Dockerfile                  # 应用镜像
├── pyproject.toml              # 项目元数据 + 工具配置
├── requirements.txt            # Python 依赖
├── .env.example                # 环境变量模板
├── README.md
│
├── src/
│   ├── main.py                 # 应用入口（支持 --standalone / --reload）
│   ├── config.py               # 配置管理（自实现 .env 加载，无第三方依赖）
│   │
│   ├── gateway/                # A2A 网关层（FastAPI）
│   │   ├── server.py           # 应用工厂 + 生命周期管理
│   │   ├── router.py           # Search API 路由（/api/v1/search/*）
│   │   ├── chat_router.py      # Chat API 路由（SSE 流式 /api/v1/chat/*）
│   │   ├── middleware.py       # 限流中间件
│   │   └── session.py          # 会话管理器（Session）
│   │
│   ├── orchestrator/           # 调度编排
│   │   ├── agent.py            # Orchestrator Agent（意图解析）
│   │   └── workflow.py         # DAG 工作流引擎（Finder ∥ Encyclopedia → Calculator）
│   │
│   ├── agents/                 # 子 Agent
│   │   ├── base.py             # Agent 基类（LLM 调用封装）
│   │   ├── chat/               # Chat Agent（多轮对话入口 + 意图路由）
│   │   │   ├── agent.py        # 支持: 新搜索/追问/对比/详情/闲聊
│   │   │   └── prompts.py
│   │   ├── finder/             # 商品搜索 Agent
│   │   │   ├── agent.py        # 闲鱼 MCP 搜索 → LLM 数据清洗
│   │   │   └── prompts.py
│   │   ├── encyclopedia/       # 商品百科 Agent
│   │   │   ├── agent.py        # 纯 LLM 方案（依赖模型训练数据，无需爬虫）
│   │   │   └── prompts.py
│   │   └── calculator/         # 性价比计算 Agent
│   │       ├── agent.py        # 规则引擎 + LLM 综合评分
│   │       └── prompts.py
│   │
│   ├── a2a/                    # A2A 分布式通信
│   │   ├── launcher.py         # A2A 启动器（多进程管理 Agent 微服务）
│   │   ├── agent_apps.py       # Agent 服务应用工厂
│   │   ├── client.py           # A2A HTTP 客户端
│   │   └── server.py           # A2A 服务端接口
│   │
│   ├── mcp/                    # MCP Server
│   │   ├── xianyu_server.py    # 闲鱼 MCP Server（cookie 登录，真实搜索）
│   │   └── tools.py            # MCP 工具定义
│   │
│   ├── models/                 # 数据模型
│   │   ├── database.py         # 数据库连接（异步 SQLAlchemy）
│   │   ├── orm.py              # ORM 模型（SearchLog / XianyuItem / ProductCache / AnalysisResult）
│   │   └── schemas.py          # Pydantic 模型（API 请求/响应、Agent 间通信）
│   │
│   └── utils/                  # 工具函数
│       └── logger.py           # Loguru 日志配置
│
├── tests/                      # 测试
│   ├── conftest.py
│   ├── test_calculator.py
│   ├── test_chat.py
│   ├── test_finder.py
│   ├── test_log.py
│   └── test_xianyu.py
│
└── scripts/
    └── init_db.sql             # 数据库初始化
```

## 核心流程

### 工作流 DAG

```
Orchestrator (解析意图: 商品名/品牌/型号/预算)
      │
  ┌───┴───┐
  ▼       ▼
Finder  Encyclopedia  (并行执行，无数据依赖)
  │       │
  └───┬───┘
      ▼
 Calculator (依赖前两者全部完成)
      │
      ▼
  最终结果 + 持久化到 MySQL
```

### Chat Agent 意图路由

```
用户消息 → ChatAgent 意图分析
              │
   ┌──────────┼──────────┬──────────┬──────────┐
   ▼          ▼          ▼          ▼          ▼
新搜索      追问       对比      查看详情    闲聊
(触发完整   (基于历史   (多商品    (单商品     (打招呼/
 Workflow)  上下文回答)  横评)     详情分析)   通用咨询)
```

### 各 Agent 职责

1. **Orchestrator** — 用 LLM 解析用户自然语言，提取商品名称、品牌、型号、预算范围、成色偏好、地区
2. **Finder Agent** — 调用闲鱼 MCP Server 搜索二手商品 → LLM 规范化清洗数据 → 输出 TOP N 商品列表
3. **Encyclopedia Agent** — 纯 LLM 方案，不依赖爬虫，利用 DeepSeek 训练数据提供新品规格、渠道价格、评分、上市时间等百科信息
4. **Calculator Agent** — 规则引擎计算折扣率 + LLM 生成购买建议 → 输出性价比评分和最终结论
5. **Chat Agent** — 多轮对话入口，智能路由用户意图，管理会话上下文，SSE 流式推送进度

## 运行测试

```bash
# 运行所有测试
pytest tests/ -v

# 运行特定模块测试
pytest tests/test_calculator.py -v

# 带覆盖率
pytest tests/ --cov=src --cov-report=html
```

## 配置说明

项目使用自实现的 `.env` 加载机制（`src/config.py`），不依赖 pydantic-settings。配置优先级：**环境变量 > .env > 默认值**。

关键环境变量：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 | - |
| `DEEPSEEK_MODEL` | 模型名称 | `deepseek-chat` |
| `OPENAI_API_KEY` | OpenAI API 密钥（备用） | - |
| `XIANYU_COOKIE` | 闲鱼 Cookie（不填则用模拟数据） | - |
| `A2A_ENABLED` | 是否启用 A2A 分布式模式 | `true` |
| `API_HOST` / `API_PORT` | 网关监听地址 | `0.0.0.0:8000` |
| `MYSQL_*` | 数据库连接信息 | `localhost:3306` |
| `REDIS_*` | Redis 连接信息 | `localhost:6379` |

## A2A 分布式架构（可选）

```bash
# 启动全部 Agent 微服务（多进程）
python -m src.a2a.launcher
#   Workflow:      8001
#   Finder:        8002
#   Encyclopedia:  8003
#   Calculator:    8004

# 启动单个服务
python -m src.a2a.launcher --service finder

# 然后以 A2A 模式启动网关（A2A_ENABLED=true）
python -m src.main
```

## 待完成

- [ ] 闲鱼 MCP Server 接入真实 API（当前需配置 Cookie 登录）
- [ ] 百科 Agent 接入网页抓取（当前走纯 LLM 训练数据）
- [ ] Redis 缓存层（百科数据缓存、请求限流持久化、进度状态存储）
- [ ] WebSocket 实时进度推送（当前使用 SSE + 轮询混合）
- [ ] 前端 Web UI
- [ ] 用户认证与历史记录

## License

[TODO]