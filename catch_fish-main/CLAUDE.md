# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在此仓库中工作时提供指导。

## 项目概述

catch_fish 是一个多智能体系统，帮助用户在闲鱼上搜索二手商品，与京东/天猫的全新商品价格进行对比，并提供性价比分析。系统基于 FastAPI 构建，使用自定义的 A2A（Agent-to-Agent，智能体间通信）协议，并通过 MCP（Model Context Protocol，模型上下文协议）集成工具。

## 常用命令

```bash
# 开发服务器（带热重载）
uvicorn src.main:app --reload --port 8000

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

## 架构：智能体工作流 DAG

核心执行路径为 `CatchFishWorkflow.execute()`（位于 `src/orchestrator/workflow.py`），运行一个固定的有向无环图（DAG）：

```
Orchestrator（编排器，从自然语言中解析意图）
       │
  ┌────┴────┐
  ▼         ▼
Finder   Encyclopedia    ← 两者并行执行（asyncio.gather）
  │         │
  └────┬────┘
       ▼
   Calculator            ← 等待上游两个智能体完成后才执行
```

- **Orchestrator**（编排器，`src/orchestrator/agent.py`）：LLM 将自然语言解析为 `ParsedIntent`（包含 product_name、brand、model、specs、budget、condition、location）。
- **Finder**（搜寻器，`src/agents/finder/agent.py`）：调用闲鱼 MCP 搜索二手商品。当 MCP 客户端不可用时（开发模式），回退到 LLM 生成的模拟数据。
- **Encyclopedia**（百科器，`src/agents/encyclopedia/agent.py`）：抓取京东/天猫的全新商品价格和规格，并通过 LLM 研究进行丰富。`scrapers.py` 中的抓取器以尽力而为模式返回数据；抓取失败不会中断整个工作流。
- **Calculator**（计算器，`src/agents/calculator/agent.py`）：两阶段分析——首先使用确定性规则引擎（`scoring.py`）对每个商品打分，然后由 LLM 进行定性深度分析并撰写最终结论。规则引擎提供底线评分，LLM 负责补充细节。

## 智能体基类

所有智能体均继承 `BaseAgent`（`src/agents/base.py`），该基类提供：
- 延迟初始化 `anthropic.AsyncAnthropic` 客户端（从配置中读取 `ANTHROPIC_API_KEY`）
- `ask_llm()` — 返回原始文本，带自动重试（使用 tenacity 库）
- `ask_llm_json()` — 调用 `ask_llm()` 后从响应中提取 JSON（能处理 ```json 代码块和裸 JSON 对象）
- 抽象方法 `execute(**kwargs) -> Any`，每个智能体必须实现
- 抽象方法 `system_prompt() -> str`，每个智能体必须重写

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

## API 设计（异步任务模式）

网关（`src/gateway/router.py`）采用"提交-轮询"模式：
1. `POST /api/v1/search` — 接收 `SearchRequest`，返回 `202` 和 `search_id`，并启动后台任务
2. `GET /api/v1/search/{id}/status` — 返回各智能体的进度（pending/running/done/failed）
3. `GET /api/v1/search/{id}/result` — 返回完整的 `SearchResultResponse`，若未完成则返回 404

结果保存在内存缓存 `_results_cache: dict[str, SearchResultResponse]` 中。生产环境需要使用 Redis 或数据库持久化存储。

## 闲鱼 MCP 服务器

`src/mcp/xianyu_server.py` 是一个使用官方 `mcp` 包构建的 MCP 服务器骨架。注册了三个工具（`search_items`、`get_item_detail`、`get_seller_info`），但目前均返回占位数据。`_handle_search_items` 中的 `TODO` 标记指明了需要接入真实闲鱼 API 的位置。`src/mcp/tools.py` 定义了工具的模式（Pydantic 输入模型 + MCP Tool 定义）。

## 配置

`src/config.py` 使用 `pydantic-settings` 从 `.env` 文件加载配置。关键环境变量：
- `ANTHROPIC_API_KEY`（任何 LLM 调用必需）
- `DATABASE_URL` / `DATABASE_URL_ASYNC`（MySQL，异步使用 `aiomysql` 驱动）
- `REDIS_URL`（可选，尚未接入代码）
- `XIANYU_COOKIE`（用于真实 API 访问，尚未使用）

## 数据库（开发阶段可选）

在 `src/models/orm.py`（SQLAlchemy）和 `scripts/init_db.sql`（原始 DDL）中均定义了四张表：`search_log`、`xianyu_items`、`product_cache`、`analysis_result`。应用可在没有 MySQL 的情况下启动——`init_db()` 失败时仅记录警告日志，不会导致致命错误。

## 多轮对话架构 (Chat)

用户通过 `POST /api/v1/chat`（SSE 流式）进行多轮交互。

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
| `new_search` | 新商品搜索请求 | 触发完整 Orchestrator 工作流，结果绑定到 session |
| `follow_up` | 追问如"第三个怎么样" | 从 session.search_context 取出对应商品，LLM 深度分析 |
| `compare` | 对比如"1和3哪个好" | 取出指定商品，LLM 多维度对比 |
| `detail` | 查看卖家/详情 | 从 session 取商品信息，LLM 生成详细解读 |
| `general_chat` | 闲聊/咨询 | 直接 LLM 回复，不触发搜索 |

### 会话存储 (`src/gateway/session.py`)

- `Session` 持有消息历史 + 最后一次搜索结果（`search_context`）
- `SessionManager` 全局单例，内存存储，支持 `create/get/delete/cleanup`
- 会话 TTL 默认 2 小时
- `session.get_item_by_index(3)` — 用户说"第三个"时定位具体商品

### SSE 事件流

客户端连接 `POST /api/v1/chat` 后收到的事件序列：

```
session → progress* → message → result? → done
```

- `session`: 返回 session_id，客户端保存用于后续请求
- `progress`: Agent 执行阶段（orchestrating / searching / calculating / completed）
- `message`: 最终 AI 回复文本
- `result`: 结构化搜索结果（仅新搜索时）
- `done`: 流结束
