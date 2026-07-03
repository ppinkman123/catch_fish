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
                  ┌────────────────────┼────────────────────┐
                  ▼                    ▼                    ▼
         ┌──────────────┐  ┌──────────────────┐  ┌────────────────┐
         │ Finder Agent │  │Encyclopedia Agent│  │Calculator Agent│
         │  (闲鱼搜索)    │  │  (新品信息采集)    │  │  (性价比分析)    │
         └──────┬───────┘  └────────┬─────────┘  └────────┬───────┘
                │                   │                      │
                ▼                   ▼                      ▼
         ┌──────────────┐  ┌──────────────────┐  ┌────────────────┐
         │ 闲鱼 MCP     │  │ 网页抓取器        │  │ 规则引擎+LLM   │
         │ Server       │  │ (JD/Tmall/官网)   │  │ 综合评分       │
         └──────────────┘  └──────────────────┘  └────────────────┘
```

## 技术栈

| 组件 | 技术 |
|------|------|
| 语言 | Python 3.11+ |
| Web 框架 | FastAPI |
| AI Agent | 自研 Agent 框架 + Anthropic Claude API |
| 协议 | A2A (JSON/HTTP) + MCP |
| 网页解析 | BeautifulSoup4 / lxml / parsel |
| 数据库 | MySQL 8.0 + SQLAlchemy (异步) |
| 缓存 | Redis 7 |
| 部署 | Docker + Docker Compose |

## 快速开始

### 前置条件

- Python 3.11+
- Docker & Docker Compose（或本地 MySQL + Redis）
- Anthropic API Key

### 安装

```bash
# 1. 克隆项目
git clone <your-repo-url> catch_fish
cd catch_fish

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入你的 ANTHROPIC_API_KEY

# 3. 安装依赖
pip install -r requirements.txt

# 4. 启动服务（Docker Compose 一键部署）
docker compose up -d

# 5. 访问 API 文档
open http://localhost:8000/docs
```

### 本地开发

```bash
# 仅启动 MySQL 和 Redis
docker compose up -d mysql redis

# 本地运行 FastAPI
uvicorn src.main:app --reload --port 8000
```

## API 接口

### 发起搜索

```bash
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
```

### 查询进度

```bash
curl http://localhost:8000/api/v1/search/a1b2c3d4/status
```

### 获取结果

```bash
curl http://localhost:8000/api/v1/search/a1b2c3d4/result
```

## 项目目录结构

```
catch_fish/
├── docker-compose.yml          # Docker 编排
├── Dockerfile                  # 应用镜像
├── requirements.txt            # Python 依赖
├── .env.example                # 环境变量模板
├── README.md
│
├── src/
│   ├── main.py                 # FastAPI 入口
│   ├── config.py               # 配置管理
│   ├── gateway/                # A2A 网关层
│   │   ├── server.py           # FastAPI 应用工厂
│   │   ├── router.py           # API 路由
│   │   └── middleware.py       # 中间件
│   ├── orchestrator/           # 调度编排
│   │   ├── agent.py            # Orchestrator Agent
│   │   └── workflow.py         # DAG 工作流
│   ├── agents/                 # 子 Agent
│   │   ├── base.py             # Agent 基类
│   │   ├── finder/             # 商品搜索 Agent
│   │   ├── encyclopedia/       # 商品百科 Agent
│   │   └── calculator/         # 性价比计算 Agent
│   ├── mcp/                    # MCP Server
│   │   ├── xianyu_server.py
│   │   └── tools.py
│   ├── models/                 # 数据模型
│   │   ├── database.py         # 数据库连接
│   │   ├── orm.py              # SQLAlchemy 模型
│   │   └── schemas.py          # Pydantic 模型
│   └── utils/                  # 工具函数
│       ├── http_client.py
│       └── logger.py
│
├── tests/                      # 测试
└── scripts/
    └── init_db.sql             # 数据库初始化
```

## 运行测试

```bash
# 运行所有测试
pytest tests/ -v

# 运行特定模块测试
pytest tests/test_calculator.py -v

# 带覆盖率
pytest tests/ --cov=src --cov-report=html
```

## 核心流程

1. **Orchestrator** 解析用户意图 → 提取商品名称、型号、预算
2. **Finder Agent** 调用闲鱼 MCP 搜索二手商品 → 整理 TOP N 商品列表
3. **Encyclopedia Agent** 从京东/天猫/官网抓取新品价格和规格 → 建立基准线
4. **Calculator Agent** 用规则引擎 + LLM 计算性价比 → 输出购买建议

## 待完成

- [ ] 闲鱼 MCP Server 接入真实 API（当前为占位实现）
- [ ] 数据库持久化（搜索结果写入 MySQL）
- [ ] Redis 缓存层（百科数据缓存、请求限流）
- [ ] WebSocket 实时进度推送
- [ ] 前端 Web UI
- [ ] 用户认证与历史记录

## License

[TODO]
