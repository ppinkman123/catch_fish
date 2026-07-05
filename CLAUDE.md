# CLAUDE.md

本文件为 AI 编码助手在此仓库中工作时提供指导。

## 项目概述

catch_fish 是一个多智能体系统，帮助用户在闲鱼上搜索二手商品，与京东/天猫的全新商品价格进行对比，并提供性价比分析。系统基于 FastAPI 构建，支持两种运行模式：
- **单进程模式**（`--standalone`）：所有 Agent 在进程内直接调用，适合开发调试
- **A2A 分布式模式**：每个 Agent 作为独立 HTTP 服务运行，通过自定义 A2A 协议通信

## 常用命令

```bash
# 单进程模式（推荐开发用，一条命令启动全部功能）
python -m src.main --standalone

# 单进程 + 热重载
python -m src.main --standalone --reload

# A2A 分布式模式 — 终端1：启动所有 Agent 子服务（端口 8001-8004）
python -m src.a2a.launcher

# A2A 分布式模式 — 终端2：启动 Gateway（端口 8000）
python -m src.main

# 开发模式快捷方式（等同于 --standalone + reload）
python -m src.a2a.launcher --dev

# Docker：仅启动基础设施（MySQL + Redis）
docker compose up -d mysql redis

# Docker：启动全部服务（app + MySQL + Redis）
docker compose up -d

# 测试
pytest tests/ -v                          # 全部测试
pytest tests/test_calculator.py -v        # 仅评分引擎（无 LLM 依赖）
pytest tests/ --cov=src --cov-report=html # 带覆盖率报告

# 语法检查（无需安装依赖）
python -m py_compile src/config.py
```

## 两种运行模式详解

### 单进程模式（`--standalone`）
- 设置环境变量 `A2A_ENABLED=false`，所有 Agent 在 Gateway 进程内直接实例化调用
- 无需启动外部 Agent 服务，适合开发和调试
- 对应启动命令：`python -m src.main --standalone`

### A2A 分布式模式
- Gateway（8000）通过 HTTP 调用 Workflow（8001），Workflow 再通过 HTTP 调用 Finder（8002）、Encyclopedia（8003）、Calculator（8004）
- 每个 Agent 是独立的 FastAPI 进程，通过 `src/a2a/server.py` 的 `create_agent_app()` 包装
- 必须先启动 Agent 服务（`python -m src.a2a.launcher`），再启动 Gateway（`python -m src.main`）
- 端口分配：

| 服务 | 端口 | 环境变量 |
|------|------|----------|
| Gateway | 8000 | `API_PORT` |
| Workflow | 8001 | `A2A_WORKFLOW_URL` |
| Finder | 8002 | `A2A_FINDER_URL` |
| Encyclopedia | 8003 | `A2A_ENCYCLOPEDIA_URL` |
| Calculator | 8004 | `A2A_CALCULATOR_URL` |

## 架构：A2A 模块（`src/a2a/`）

A2A（Agent-to-Agent）模块将单体 Agent 拆分为独立 HTTP 服务：

| 文件 | 职责 |
|------|------|
| `server.py` | `create_agent_app(agent)` — 将任意 BaseAgent 包装为 FastAPI 应用，自动从 `execute()` 签名推断输入 schema，暴露 `POST /execute` 和 `GET /agent-card` |
| `client.py` | `A2AClient` — 异步 HTTP 客户端，支持 Agent 注册表、自动序列化 Pydantic 模型、并行调用（`gather()`） |
| `agent_apps.py` | 工厂函数 — `create_finder_app()`、`create_encyclopedia_app()`、`create_calculator_app()`、`create_workflow_app()` |
| `launcher.py` | 多进程启动器 — 使用 `multiprocessing` 管理 4 个 Agent 子进程，支持 `--service` 单独启动、`--dev` 单进程模式 |

## 架构：智能体工作流 DAG

核心执行路径为 `CatchFishWorkflow.execute()`（位于 `src/orchestrator/workflow.py`），运行一个固定的有向无环图（DAG）：

```
Orchestrator（编排器，从自然语言中解析意图）
       │
  ┌────┴────┐
  ▼         ▼
Finder    Encyclopedia    ← 两者并行执行（asyncio.gather）
  │         │
  └────┬────┘
       ▼
   Calculator            ← 等待上游两个智能体完成后才执行
```

### 各 Agent 详解

- **Orchestrator**（编排器，`src/orchestrator/agent.py`）：LLM 将自然语言解析为 `ParsedIntent`（包含 product_name、brand、model、specs、budget、condition、location）。同时包含 `WorkflowAgent`，将 `CatchFishWorkflow` 包装为标准 BaseAgent，供 A2A 服务化使用。

- **Finder**（搜寻器，`src/agents/finder/agent.py`）：调用闲鱼 MCP 搜索二手商品。当 MCP 客户端不可用时（开发模式），回退到 LLM 生成的模拟数据。MCP 原始数据经 `_truncate_raw_results()` 截断后再发给 LLM 规范化——最多取 5 条、每条字段截断到 500 字，`max_tokens=8192`，防止响应被截断。

- **Encyclopedia**（百科器，`src/agents/encyclopedia/agent.py`）：纯 LLM 方案，依靠模型训练数据提供新品规格、价格、口碑，无需爬虫。

- **Calculator**（计算器，`src/agents/calculator/agent.py`）：两阶段分析——首先使用确定性规则引擎（`scoring.py`）对每个商品打分，然后由 LLM 进行定性深度分析并撰写最终结论。规则引擎提供底线评分，LLM 负责补充细节。

- **WorkflowAgent**（`src/orchestrator/agent.py`）：将 `CatchFishWorkflow` 包装为 BaseAgent，支持通过 A2A 客户端调用远程子 Agent 或进程内直接调用。作为 A2A 服务运行时是 Gateway 调用的唯一入口。

### CatchFishWorkflow 两种调用模式

`CatchFishWorkflow.__init__` 接受可选的 `a2a_client` 参数：
- **直接模式**（`a2a_client=None`）：本地实例化 Finder、Encyclopedia、Calculator，进程内直接调用
- **A2A 模式**（传入 A2AClient）：通过 HTTP 调用远程 Agent 服务（`_step_find`、`_step_research`、`_step_calculate` 方法均有分支判断）

### 数据库持久化

工作流执行过程中自动写入 MySQL 四张表（失败时仅警告，不阻断流程）：

| 表 | 写入时机 | 内容 |
|----|----------|------|
| `search_log` | 工作流启动时创建，每阶段更新 status | 搜索记录、意图 JSON、状态流转 |
| `xianyu_items` | Finder 完成后 | 闲鱼商品快照 |
| `product_cache` | Encyclopedia 完成后 | 百科信息缓存（按产品名去重，24h 过期） |
| `analysis_result` | Calculator 完成后 | 性价比分析报告 |

## 智能体基类

所有智能体均继承 `BaseAgent`（`src/agents/base.py`），该基类提供：
- 延迟初始化 `AsyncOpenAI` 客户端（从配置中读取 `DEEPSEEK_API_KEY`，兼容 DeepSeek / OpenAI API）
- `ask_llm()` — 返回原始文本，带自动重试（使用 tenacity 库），支持 `max_tokens` 参数覆盖默认值
- `ask_llm_json()` — 调用 `ask_llm()` 后从响应中提取 JSON（能处理 ```json 代码块和裸 JSON 对象，空响应时抛出明确错误）
- 抽象方法 `execute(**kwargs) -> Any`，每个智能体必须实现
- 抽象方法 `system_prompt() -> str`，每个智能体必须重写

### LLM 响应被截断的常见原因

当 LLM 需要输出大量结构化 JSON（如 Finder 规范化多条商品）时，默认 `deepseek_max_tokens=4096` 可能不够：
- **症状**：`Unterminated string` / `Expecting value: line 1 column 1 (char 0)` / 空响应
- **修复**：调用 `ask_llm_json()` 时传入更大的 `max_tokens`（如 `max_tokens=8192`）；同时减少输入数据量（截断条数、字段长度）

## 评分引擎（基于规则，无需 LLM）

`src/agents/calculator/scoring.py` 是唯一可以不依赖 API Key 进行测试的模块。它计算 0-100 的综合评分：

| 维度 | 权重 | 计算逻辑 |
|-----------|--------|-------|
| 折扣率 | 40% | `二手价格 / 全新价格` — 线性评分，0.35x → 40 分，0.90x → 10 分 |
| 成色 | 25% | 从自由文本归一化为标准枚举：like_new=25，excellent=22，good=16，acceptable=8，poor=3 |
| 卖家信用 | 15% | ≥800=15 分，≥700=12 分，≥600=8 分，低于=3 分 |
| 市场供给 | 10% | ≥50 个商品=10 分，≥20=7 分，≥5=5 分，更少=3 分 |
| 折旧程度 | 10% | 距发布日期月数：≤3 月=9.5，≤6 月=9，≤12 月=8，≤24 月=6.5，更久=5 |

`normalize_condition()` 函数将中文成色描述（"99新"、"仅拆封"、"轻微划痕"）映射到标准枚举值。

## 智能体之间的数据流

各智能体的输出为 `src/models/schemas.py` 中定义的 Pydantic 模型：

- `Orchestrator` → `ParsedIntent`
- `Finder` → `FinderResult`（包含 `list[XianyuItemOut]`）
- `Encyclopedia` → `EncyclopediaResult`（包含 `list[ChannelPrice]`、规格、最低全新价格）
- `Calculator` 消费 `FinderResult` + `EncyclopediaResult` → `CalculatorResult`（包含 `Recommendation`、`MarketSummary`、结论文本）
- 最终：`SearchResultResponse` 封装以上三个输出

## API 设计

### 搜索接口（异步任务模式）

网关（`src/gateway/router.py`）采用"提交-轮询"模式：
1. `POST /api/v1/search` — 接收 `SearchRequest`，返回 `202` 和 `search_id`，并启动后台任务
2. `GET /api/v1/search/{id}/status` — 返回各智能体的进度（pending/running/done/failed）
3. `GET /api/v1/search/{id}/result` — 返回完整的 `SearchResultResponse`，若未完成则返回 404

结果保存在内存缓存 `_results_cache: dict[str, SearchResultResponse]` 中。生产环境需要使用 Redis 或数据库持久化存储。

### 多轮对话接口（SSE 流式）

用户通过 `POST /api/v1/chat`（SSE 流式）进行多轮交互。详见下方"多轮对话架构"章节。

## 闲鱼 MCP 服务器

`src/mcp/xianyu_server.py` 逆向闲鱼 MTOP API，实现三个工具：`search_items`、`get_item_detail`、`get_seller_info`。

### MTOP 签名机制

闲鱼后端使用淘系 MTOP（Mobile Taobao Open Platform）网关。每次 API 调用需要：

1. 从 Cookie 取 `_m_h5_tk` 前 32 位作为 token
2. 签名串：`token & UTC毫秒时间戳 & APP_KEY(34839810) & 请求体JSON`
3. MD5 后作为 `sign` 参数附加到 GET 请求

相关函数：`_extract_token()`、`_make_sign()`、`_utc_timestamp_ms()`、`_call_mtop_api()`。

### 响应解析

MTOP 搜索接口返回结构为：

```
result.data.resultList[]                     # 商品列表
    .data.item.main                          # 每个商品的核心数据
        .title                               # 标题
        .picUrl                              # 主图
        .oriPrice                            # 原价（如 "¥39.90"）
        .userNickName                        # 卖家昵称
        .userFishShopLabel.tagList[].data.content  # 店铺评价/好评率
        .clickParam.args.{id, price, seller_id, p_city, publishTime}  # 基础字段
        .exContent.area                      # 发货地
        .exContent.detailParams.title        # 完整描述（比 main.title 更长）
        .exContent.fishTags.*.tagList[].data.content  # 商品标签（尺寸/成色/信用等）
```

`_parse_mtop_search_result()` 负责原样提取上述字段，**不做品类识别、品牌猜测、属性分类**——这些留给上游 LLM。

### 直接测试

文件顶部 `sys.path.insert()` 确保可以直接执行：

```bash
python src/mcp/xianyu_server.py "卡西欧"
```

未传 Cookie 时 MTOP API 调用失败，返回空结果。配置好 `XIANYU_COOKIE` 后即可获取真实数据。

`src/mcp/tools.py` 定义了工具的模式（Pydantic 输入模型 + MCP Tool 定义）。

## 配置

`src/config.py` 使用手动 `.env` 解析（不依赖 pydantic-settings）。`Settings` 类从 `.env` 文件和环境变量加载配置，优先级：环境变量 > .env > 默认值。

关键环境变量：
- `DEEPSEEK_API_KEY`（任何 LLM 调用必需）
- `DEEPSEEK_BASE_URL`（默认 `https://api.deepseek.com`）
- `DEEPSEEK_MODEL`（默认 `deepseek-chat`）
- `DATABASE_URL` / `DATABASE_URL_ASYNC`（MySQL，异步使用 `aiomysql` 驱动）
- `REDIS_URL`（可选，尚未接入代码）
- `XIANYU_COOKIE`（闲鱼 MTOP API 签名必需，需包含 `_m_h5_tk`）
- `A2A_ENABLED`（默认 `true`，设为 `false` 走单进程直接调用）
- `A2A_WORKFLOW_URL` / `A2A_FINDER_URL` / `A2A_ENCYCLOPEDIA_URL` / `A2A_CALCULATOR_URL`

## 数据库（开发阶段可选）

在 `src/models/orm.py`（SQLAlchemy）中定义了四张表：`search_log`、`xianyu_items`、`product_cache`、`analysis_result`。`src/models/database.py` 使用异步引擎（`create_async_engine`），延迟初始化。

应用可在没有 MySQL 的情况下启动——`init_db()` 失败时仅记录警告日志，不会导致致命错误。工作流中的数据库写入操作失败也仅记录警告，不会阻断主流程。

## 多轮对话架构 (Chat)

用户通过 `POST /api/v1/chat`（SSE 流式）进行多轮交互。

### SSE 事件流

客户端连接后收到的事件序列：

```
session → progress* → message → result? → done
```

- `session`: 返回 session_id，客户端保存用于后续请求
- `progress`: Agent 执行阶段（orchestrating / searching / calculating / completed）
- `message`: 最终 AI 回复文本
- `result`: 结构化搜索结果（仅新搜索时）
- `done`: 流结束

### 会话生命周期

```
用户首条消息 → 自动创建 session → 意图路由 → 搜索/追问/闲聊
用户追问     → 恢复 session    → 基于上下文 + 搜索结果响应
会话空闲 > 2h → 自动过期清理
```

### 意图路由 (ChatAgent)

`src/agents/chat/agent.py` 是对话的唯一入口，每轮都做意图路由：

| 意图 | 触发条件 | 处理方式 |
|------|----------|----------|
| `new_search` | 新商品搜索请求 | 触发完整工作流（A2A 模式下通过 HTTP 调用 Workflow 服务），结果绑定到 session |
| `follow_up` | 追问如"第三个怎么样" | 从 session.search_context 取出对应商品，LLM 深度分析 |
| `compare` | 对比如"1和3哪个好" | 取出指定商品，LLM 多维度对比 |
| `detail` | 查看卖家/详情 | 从 session 取商品信息，LLM 生成详细解读 |
| `general_chat` | 闲聊/咨询 | 直接 LLM 回复，不触发搜索 |

ChatAgent 同样支持 A2A 模式：传入 `a2a_client` 后，新搜索时通过 HTTP 调用 Workflow 服务而非本地实例化 `CatchFishWorkflow`。

### 会话存储 (`src/gateway/session.py`)

- `Session` 持有消息历史 + 最后一次搜索结果（`search_context`）
- `SessionManager` 全局单例，内存存储，支持 `create/get/delete/cleanup`
- 会话 TTL 默认 2 小时
- `session.get_item_by_index(3)` — 用户说"第三个"时定位具体商品

## 项目文件结构

```
src/
├── main.py                    # 应用入口，解析 --standalone/--reload 参数
├── config.py                  # 全局配置（手动 .env 解析）
├── a2a/                       # A2A 分布式模块
│   ├── __init__.py            # 导出 create_agent_app, A2AClient, get_client
│   ├── server.py              # create_agent_app() — BaseAgent → FastAPI app
│   ├── client.py              # A2AClient — 异步 HTTP 客户端 + 全局单例
│   ├── agent_apps.py          # 各 Agent 的 FastAPI app 工厂函数
│   └── launcher.py            # 多进程启动器
├── agents/                    # 智能体
│   ├── base.py                # BaseAgent 抽象基类
│   ├── chat/                  # 对话入口 + 意图路由
│   │   ├── agent.py           # ChatAgent
│   │   └── prompts.py         # 对话 prompt 模板
│   ├── finder/                # 闲鱼商品搜索
│   │   ├── agent.py           # FinderAgent
│   │   └── prompts.py         # 搜索 prompt 模板
│   ├── encyclopedia/          # 商品百科（纯 LLM）
│   │   ├── agent.py           # EncyclopediaAgent
│   │   └── prompts.py         # 百科 prompt 模板
│   └── calculator/            # 性价比分析
│       ├── agent.py           # CalculatorAgent
│       ├── prompts.py         # 分析 prompt 模板
│       └── scoring.py         # 规则引擎（无需 LLM）
├── orchestrator/              # 工作流编排
│   ├── agent.py               # OrchestratorAgent + WorkflowAgent
│   └── workflow.py            # CatchFishWorkflow（DAG 引擎 + 数据库持久化）
├── gateway/                   # FastAPI 网关
│   ├── server.py              # create_app() 应用工厂
│   ├── router.py              # /api/v1/search 路由
│   ├── chat_router.py         # /api/v1/chat SSE 流式路由
│   ├── session.py             # Session + SessionManager
│   └── middleware.py          # 限流等中间件
├── models/                    # 数据模型
│   ├── schemas.py             # Pydantic 模型（API 请求/响应、Agent 间通信）
│   ├── orm.py                 # SQLAlchemy ORM 模型
│   └── database.py            # 数据库连接管理（异步引擎）
├── mcp/                       # MCP 工具
│   ├── xianyu_server.py       # 闲鱼 MTOP API 逆向
│   └── tools.py               # MCP Tool 定义
└── utils/
    └── logger.py              # 日志工具
```
