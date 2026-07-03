# 闲鱼商品获取与性价比分析系统 — 项目规格书

> **使用说明**：请根据实际情况填写所有 `[TODO]` 标记的内容。

---

## 一、项目概述

| 字段 | 内容 |
|------|------|
| **项目名称** | `[TODO: 项目名称，如 xianyu-agent-hub]` |
| **项目目标** | 用户通过自然语言描述需求 → A2A 网关调度多 Agent 协作 → 自动搜索闲鱼二手商品 → 获取新品百科资料 → 计算性价比 → 返回推荐结果 |
| **目标用户** | `[TODO: 如 普通消费者 / 数码爱好者 / 二手交易商]` |
| **核心价值** | 让用户快速了解"买二手是否划算"，用数据驱动二手交易决策 |

---

## 二、系统架构

```
┌──────────────────────────────────────────────────────────────────┐
│                        用户终端 (User Client)                     │
│                    Web UI / CLI / Chat Interface                  │
└─────────────────────────────┬────────────────────────────────────┘
                              │  A2A Protocol (HTTP/JSON-RPC)
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                     A2A 网关 (A2A Gateway)                        │
│              FastAPI + A2A Protocol Handler                      │
│      - 请求路由 / 鉴权 / 限流 / 会话管理                           │
└─────────────────────────────┬────────────────────────────────────┘
                              │  任务分发
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                Orchestrator Agent (调度编排器)                     │
│      - 解析用户意图 → 拆解子任务 → 编排执行顺序                     │
│      - 3 个子 Agent 按 DAG 工作流执行                              │
└──────┬──────────────────────┬────────────────────────┬───────────┘
       │ 子任务1               │ 子任务2                │ 子任务3
       ▼                       ▼                        ▼
┌──────────────┐   ┌──────────────────┐   ┌──────────────────────┐
│ 商品搜索Agent │   │  商品百科Agent    │   │  性价比计算Agent      │
│ (Finder)     │   │  (Encyclopedia)  │   │  (Calculator)        │
│              │   │                  │   │                      │
│ 调用闲鱼MCP  │   │ 从网页抓取新品    │   │ 对比新品 vs 二手     │
│ 搜索二手商品 │   │ 规格/价格/口碑   │   │ 多维度计算性价比      │
└──────┬───────┘   └────────┬─────────┘   └──────────┬───────────┘
       │                    │                        │
       ▼                    ▼                        ▼
┌──────────────┐   ┌──────────────────┐   ┌──────────────────────┐
│  闲鱼 MCP    │   │  网页抓取工具     │   │  价格对比引擎         │
│  Server      │   │  (bs4/parsel)    │   │  (计算逻辑)          │
└──────────────┘   └──────────────────┘   └──────────────────────┘
       │                    │
       ▼                    ▼
┌──────────────┐   ┌──────────────────┐
│   闲鱼API    │   │  目标网页        │
│  (外部服务)   │   │  (京东/淘宝/官网) │
└──────────────┘   └──────────────────┘

                          │ 结果汇总
                          ▼
┌──────────────────────────────────────────────────────────────────┐
│                        数据存储层 (MySQL)                         │
│   - 商品索引表 / 搜索记录 / 百科缓存 / 性价比分析结果              │
└──────────────────────────────────────────────────────────────────┘
```

---

## 三、技术栈明细

| 层级 | 技术选型 | 版本 | 用途说明 |
|------|----------|------|----------|
| 语言 | Python | `[TODO: 3.11+]` | 主开发语言 |
| Web框架 | FastAPI | `[TODO: 0.110+]` | A2A 网关 + REST API |
| 异步 | asyncio + httpx | `[TODO]` | 异步 HTTP 请求 |
| AI Agent 框架 | `[TODO: Google ADK / LangGraph / CrewAI / AutoGen]` | `[TODO]` | Agent 编排与 MCP 集成 |
| A2A 协议 | `[TODO: a2a-sdk / 自研]` | `[TODO]` | Agent-to-Agent 通信协议 |
| MCP 协议 | `[TODO: mcp / fastmcp]` | `[TODO]` | 闲鱼 MCP Server 实现 |
| HTML 解析 | BeautifulSoup4 / lxml / parsel | `[TODO]` | 网页商品信息抓取 |
| 数据存储 | MySQL | `[TODO: 8.0+]` | 持久化存储 |
| 缓存 | Redis (可选) | `[TODO: 7.0+]` | 百科数据缓存 / 会话管理 |
| 容器化 | Docker + Docker Compose | `[TODO]` | 一键部署 |
| CI/CD | `[TODO: GitHub Actions / 无]` | `[TODO]` | 持续集成 |
| LLM 底座 | `[TODO: DeepSeek / OpenAI / 本地模型]` | `[TODO]` | 驱动 Agent 推理 |

---

## 四、Agent 详细定义

### 4.1 Orchestrator Agent（调度编排器）

| 字段 | 内容 |
|------|------|
| **Agent ID** | `orchestrator` |
| **职责** | 解析用户自然语言输入，识别搜索意图（商品名称、预算范围、成色要求），拆解为 3 个子任务并编排执行顺序 |
| **输入** | 用户自然语言查询，如 "帮我看看 iPhone 15 Pro 256G 在闲鱼上多少钱，买二手划算吗" |
| **输出** | 结构化的子任务执行计划 (DAG)，包含任务依赖关系 |
| **Prompt 模板** | |

```
[TODO: 填写 Orchestrator 的 System Prompt]

你是一个二手商品搜索的调度专家。用户会描述他想买的商品，你需要：
1. 提取关键信息：商品名称、型号、规格、预算范围、成色偏好
2. 将任务拆解为以下子任务（按依赖关系）：
   - Task A (无依赖): 在闲鱼搜索该商品的二手列表
   - Task B (无依赖): 查找该商品的全新市场价格和规格参数
   - Task C (依赖 A+B): 综合二手价格和新品价格，计算性价比
3. 返回结构化的执行计划

输出格式：
{
  "product_name": "商品名称",
  "specs": {"型号": "...", "规格": "..."},
  "budget_range": {"min": 0, "max": 0},
  "condition_preference": "成色偏好",
  "tasks": [
    {"id": "A", "agent": "finder", "depends_on": []},
    {"id": "B", "agent": "encyclopedia", "depends_on": []},
    {"id": "C", "agent": "calculator", "depends_on": ["A", "B"]}
  ]
}
```

### 4.2 商品搜索 Agent（Finder）

| 字段 | 内容 |
|------|------|
| **Agent ID** | `finder` |
| **职责** | 调用闲鱼 MCP 工具搜索二手商品，返回商品列表（标题、价格、卖家、成色、链接） |
| **输入** | 商品名称 + 搜索参数（价格区间、地区、排序方式） |
| **输出** | 闲鱼二手商品列表（JSON） |
| **依赖** | 闲鱼 MCP Server |
| **Prompt 模板** | |

```
[TODO: 填写 Finder Agent 的 System Prompt]

你是一个闲鱼二手商品搜索助手。你可以使用闲鱼 MCP 工具搜索商品。
请根据用户要搜索的商品信息，调用合适的搜索工具。
搜索时注意：
- 使用精确的关键词提高匹配度
- 关注价格异常低的商品（可能是假货）
- 优先返回信用分高的卖家商品
- [TODO: 补充其他搜索策略]

返回格式：
{
  "items": [
    {
      "title": "商品标题",
      "price": 0.00,
      "original_price": 0.00,
      "condition": "全新/几乎全新/有使用痕迹/...",
      "seller_credit": "卖家信用分",
      "location": "发货地",
      "images": ["url1", "url2"],
      "listing_url": "闲鱼链接",
      "listed_time": "发布时间"
    }
  ],
  "total_count": 100,
  "search_time": "2024-01-01T00:00:00"
}
```

### 4.3 商品百科 Agent（Encyclopedia）

| 字段 | 内容 |
|------|------|
| **Agent ID** | `encyclopedia` |
| **职责** | 从京东/淘宝/品牌官网等渠道抓取商品的新品信息（官方价格、规格参数、用户评价） |
| **输入** | 商品名称 + 型号规格 |
| **输出** | 新品商品百科信息（JSON） |
| **依赖** | 网页抓取工具 (bs4/parsel) |
| **Prompt 模板** | |

```
[TODO: 填写 Encyclopedia Agent 的 System Prompt]

你是一个商品信息研究员。你可以使用网页抓取工具获取商品的官方信息。
请根据用户要查询的商品，从以下来源查找新品信息（按优先级）：
1. 品牌官方网站
2. 京东自营
3. 天猫旗舰店
4. [TODO: 补充其他数据源]

需要获取的信息：
- 官方建议零售价（MSRP）
- 详细规格参数
- 上市时间
- 用户评分和口碑
- 保修政策
- [TODO: 补充其他需要的信息]

返回格式：
{
  "product_name": "商品全称",
  "brand": "品牌",
  "model": "型号",
  "specs": {
    "颜色": ["选项1", "选项2"],
    "容量/规格": "...",
    "[TODO: 其他规格]": "..."
  },
  "new_price": {
    "official": 0.00,
    "jd": 0.00,
    "tmall": 0.00,
    "lowest_new": 0.00,
    "source_urls": ["url1", "url2"]
  },
  "release_date": "2024-01-01",
  "rating": 4.5,
  "warranty": "保修说明",
  "data_freshness": "2024-01-01T00:00:00"
}
```

### 4.4 性价比计算 Agent（Calculator）

| 字段 | 内容 |
|------|------|
| **Agent ID** | `calculator` |
| **职责** | 综合闲鱼二手价格与新品官方价格，多维度计算性价比，给出购买建议 |
| **输入** | Finder Agent 输出 + Encyclopedia Agent 输出 |
| **输出** | 性价比分析报告（JSON） |
| **Prompt 模板** | |

```
[TODO: 填写 Calculator Agent 的 System Prompt]

你是一个二手商品性价比分析师。根据收集到的新品和二手商品信息，计算性价比。

计算维度：
1. 价格折扣率 = 二手价 / 新品最低价 × 100%
2. 成色折旧评估：基于成色描述估算剩余价值
3. 保修价值：新品有保修，二手通常无保修，量化保修价值
4. 市场供应量：同类商品在售数量（供过于求 → 议价空间大）
5. 综合性价比评分（0-100分）
   - 90+: 强烈推荐（价格极低，成色好）
   - 70-89: 推荐购买
   - 50-69: 可以考虑
   - <50: 不建议（不如买新品）

[TODO: 补充更多计算维度和评分规则]

返回格式：
{
  "analysis": {
    "best_deal": {
      "title": "最划算的商品标题",
      "price": 0.00,
      "discount_rate": 0.65,
      "score": 85,
      "listing_url": "链接"
    },
    "recommendations": [
      {
        "title": "...",
        "price": 0.00,
        "score": 80,
        "reason": "推荐理由"
      }
    ],
    "new_product_baseline": {
      "lowest_new_price": 0.00,
      "source": "京东自营"
    },
    "market_summary": {
      "avg_used_price": 0.00,
      "price_range": {"min": 0.00, "max": 0.00},
      "total_listings": 50,
      "recommendation": "建议购买二手 / 建议购买新品 / ..."
    },
    "verdict": "综合来看，闲鱼二手XXX性价比评分为85分，比新品便宜35%，成色良好，推荐购买。但需注意... [TODO: AI 生成的总结文案]"
  }
}
```

---

## 五、MCP Server 定义（闲鱼）

### 5.1 闲鱼 MCP Server

| 字段 | 内容 |
|------|------|
| **Server 名称** | `xianyu-mcp-server` |
| **协议** | MCP (Model Context Protocol) |
| **传输方式** | `[TODO: stdio / SSE / Streamable HTTP]` |
| **认证方式** | `[TODO: Cookie / Token / OAuth]` |

### 5.2 MCP Tools 清单

#### Tool 1: `search_items`

```
功能：搜索闲鱼商品列表
输入参数：
  - keyword: string        # 搜索关键词
  - min_price: float       # 最低价格（可选）
  - max_price: float       # 最高价格（可选）
  - location: string       # 地区筛选（可选）
  - sort_by: string        # 排序方式: "price_asc" | "price_desc" | "credit" | "newest" | "default"
  - page: int              # 页码（默认1）
  - page_size: int         # 每页数量（默认20）
  - [TODO: 补充其他筛选参数，如成色、交易方式等]

输出：
  - items: array           # 商品列表
  - total_count: int       # 总结果数
  - has_more: bool         # 是否有更多结果
```

#### Tool 2: `get_item_detail`

```
功能：获取单个闲鱼商品的详细信息
输入参数：
  - item_id: string        # 商品ID

输出：
  - 完整商品信息（描述、图片、卖家信息、浏览/想要数据）
```

#### Tool 3: `get_seller_info`

```
功能：获取卖家信用信息
输入参数：
  - seller_id: string      # 卖家ID

输出：
  - credit_score: int      # 信用分
  - ratings: object        # 评价统计
  - verified: bool         # 是否实名认证
  - [TODO: 补充其他卖家信息]
```

#### Tool 4: `[TODO: 补充其他 MCP 工具]`

```
功能：[TODO]
输入参数：[TODO]
输出：[TODO]
```

---

## 六、数据库设计 (MySQL)

### 6.1 ER 图概要

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────────┐
│   search_log    │     │   product_cache  │     │   analysis_result   │
│  (搜索记录)      │────→│   (商品百科缓存)  │     │   (性价比分析结果)    │
└─────────────────┘     └──────────────────┘     └─────────────────────┘
         │                                                    
         ▼                                                    
┌─────────────────┐                                           
│  xianyu_items   │                                           
│  (闲鱼商品快照)   │                                           
└─────────────────┘                                           
```

### 6.2 建表 SQL 模板

```sql
-- 1. 搜索记录表
CREATE TABLE search_log (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id    VARCHAR(64)  NOT NULL COMMENT '会话ID',
    user_query    TEXT         NOT NULL COMMENT '用户原始查询',
    parsed_intent JSON         COMMENT 'Orchestrator 解析后的意图JSON',
    status        ENUM('pending','processing','completed','failed') DEFAULT 'pending',
    created_at    DATETIME     DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_session (session_id),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='搜索记录';

-- 2. 闲鱼商品快照表
CREATE TABLE xianyu_items (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    search_id       BIGINT       NOT NULL COMMENT '关联 search_log.id',
    xianyu_item_id  VARCHAR(64)  COMMENT '闲鱼商品ID',
    title           VARCHAR(500) COMMENT '商品标题',
    price           DECIMAL(10,2) COMMENT '售价',
    original_price  DECIMAL(10,2) COMMENT '原价标价',
    `condition`     VARCHAR(50)  COMMENT '成色',
    seller_credit   INT          COMMENT '卖家信用分',
    location        VARCHAR(100) COMMENT '发货地',
    images          JSON         COMMENT '图片URL列表',
    listing_url     VARCHAR(500) COMMENT '商品链接',
    listed_time     DATETIME     COMMENT '发布时间',
    snapshot_at     DATETIME     DEFAULT CURRENT_TIMESTAMP COMMENT '快照时间',
    FOREIGN KEY (search_id) REFERENCES search_log(id),
    INDEX idx_search (search_id),
    INDEX idx_price (price)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='闲鱼商品快照';

-- 3. 商品百科缓存表
CREATE TABLE product_cache (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    product_name    VARCHAR(300) NOT NULL COMMENT '商品名称',
    brand           VARCHAR(100) COMMENT '品牌',
    model           VARCHAR(100) COMMENT '型号',
    specs           JSON         COMMENT '规格参数JSON',
    new_prices      JSON         COMMENT '各渠道新品价格JSON',
    release_date    DATE         COMMENT '上市时间',
    rating          DECIMAL(3,2) COMMENT '评分',
    warranty        VARCHAR(500) COMMENT '保修说明',
    source_urls     JSON         COMMENT '数据来源URL',
    fetched_at      DATETIME     DEFAULT CURRENT_TIMESTAMP COMMENT '抓取时间',
    expires_at      DATETIME     COMMENT '缓存过期时间',
    UNIQUE KEY uk_product (product_name(200)),
    INDEX idx_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='商品百科缓存';

-- 4. 性价比分析结果表
CREATE TABLE analysis_result (
    id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
    search_id           BIGINT NOT NULL COMMENT '关联 search_log.id',
    best_deal_item_id   BIGINT COMMENT '关联 xianyu_items.id（最佳选择）',
    new_price_baseline  DECIMAL(10,2) COMMENT '新品基准价格',
    avg_used_price      DECIMAL(10,2) COMMENT '二手均价',
    total_listings      INT    COMMENT '二手在售数量',
    recommendations     JSON   COMMENT '推荐列表JSON',
    market_summary      JSON   COMMENT '市场总结JSON',
    verdict_text        TEXT   COMMENT 'AI 分析结论',
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (search_id) REFERENCES search_log(id),
    INDEX idx_search (search_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='性价比分析结果';

-- [TODO: 补充其他需要的表]
```

---

## 七、API 接口设计

### 7.1 A2A Gateway API

```
Base URL: [TODO: http://localhost:8000/api/v1]
```

#### 接口 1: 发起商品搜索

```
POST /search
描述：用户发起一次闲鱼商品搜索 + 性价比分析请求

Request Body:
{
  "query": "[TODO: 示例: iPhone 15 Pro 256G 黑色]",
  "options": {
    "budget_min": 0,
    "budget_max": 0,
    "condition": "all",
    "location": "[TODO: 城市]",
    "max_results": 20
  }
}

Response:
{
  "search_id": "uuid",
  "status": "accepted",
  "estimated_time": 30
}
```

#### 接口 2: 查询任务状态

```
GET /search/{search_id}/status
描述：轮询搜索任务的实时状态

Response:
{
  "search_id": "uuid",
  "status": "orchestrating | searching_xianyu | fetching_encyclopedia | calculating | completed | failed",
  "progress": {
    "finder": "done",
    "encyclopedia": "running",
    "calculator": "pending"
  },
  "partial_results": {...}
}
```

#### 接口 3: 获取分析结果

```
GET /search/{search_id}/result
描述：获取完整的性价比分析结果

Response:
{
  "search_id": "uuid",
  "product_info": {...},
  "xianyu_items": [...],
  "analysis": {...},
  "completed_at": "ISO8601"
}
```

#### 接口 4: `[TODO: 补充其他接口]`

```
[TODO: 如 商品详情查询、历史记录、收藏等]
```

---

## 八、项目目录结构

```
xianyu-agent-hub/
├── docker-compose.yml              # Docker 编排
├── Dockerfile                      # 应用镜像
├── requirements.txt                # Python 依赖
├── .env.example                    # 环境变量模板
├── README.md                       # 项目说明
│
├── src/
│   ├── main.py                     # FastAPI 入口
│   ├── config.py                   # 配置管理
│   │
│   ├── gateway/                    # A2A 网关层
│   │   ├── __init__.py
│   │   ├── server.py               # A2A 协议处理
│   │   ├── router.py               # API 路由
│   │   └── middleware.py           # 鉴权 / 限流
│   │
│   ├── orchestrator/               # 调度编排器
│   │   ├── __init__.py
│   │   ├── agent.py                # Orchestrator Agent
│   │   └── workflow.py             # DAG 工作流定义
│   │
│   ├── agents/                     # 子 Agent
│   │   ├── __init__.py
│   │   ├── finder/
│   │   │   ├── agent.py            # 商品搜索 Agent
│   │   │   └── prompts.py          # Prompt 模板
│   │   ├── encyclopedia/
│   │   │   ├── agent.py            # 商品百科 Agent
│   │   │   ├── prompts.py
│   │   │   └── scrapers.py         # 网页抓取器
│   │   └── calculator/
│   │       ├── agent.py            # 性价比计算 Agent
│   │       ├── prompts.py
│   │       └── scoring.py          # 评分算法
│   │
│   ├── mcp/                        # MCP Server
│   │   ├── xianyu_server.py        # 闲鱼 MCP Server
│   │   └── tools.py               # MCP 工具实现
│   │
│   ├── models/                     # 数据模型
│   │   ├── database.py             # MySQL 连接
│   │   ├── orm.py                  # SQLAlchemy ORM 模型
│   │   └── schemas.py              # Pydantic 模型
│   │
│   └── utils/                      # 工具函数
│       ├── http_client.py          # HTTP 异步客户端
│       └── logger.py               # 日志配置
│
├── tests/                          # 测试
│   ├── test_finder.py
│   ├── test_encyclopedia.py
│   └── test_calculator.py
│
└── scripts/                        # 运维脚本
    └── init_db.sql                 # 数据库初始化
```

---

## 九、Docker 部署配置模板

### 9.1 Dockerfile

```dockerfile
FROM python:[TODO: 3.11]-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 9.2 docker-compose.yml

```yaml
version: '3.8'
services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=mysql+pymysql://user:password@mysql:3306/xianyu_hub
      - REDIS_URL=redis://redis:6379/0
      - LLM_API_KEY=${LLM_API_KEY}
      - LLM_BASE_URL=${LLM_BASE_URL}
      - [TODO: 补充其他环境变量]
    depends_on:
      mysql:
        condition: service_healthy
      redis:
        condition: service_started
    restart: unless-stopped

  mysql:
    image: mysql:[TODO: 8.0]
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD}
      MYSQL_DATABASE: xianyu_hub
      MYSQL_USER: user
      MYSQL_PASSWORD: ${MYSQL_PASSWORD}
    ports:
      - "3306:3306"
    volumes:
      - mysql_data:/var/lib/mysql
      - ./scripts/init_db.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:[TODO: 7]-alpine
    ports:
      - "6379:6379"
    restart: unless-stopped

volumes:
  mysql_data:
```

---

## 十、环境变量 (.env.example)

```bash
# ---- 数据库 ----
MYSQL_ROOT_PASSWORD=[TODO]
MYSQL_PASSWORD=[TODO]
DATABASE_URL=mysql+pymysql://user:[TODO]@mysql:3306/xianyu_hub

# ---- Redis ----
REDIS_URL=redis://redis:6379/0

# ---- LLM 配置 ----
LLM_API_KEY=[TODO: 你的 API Key]
LLM_BASE_URL=[TODO: https://api.deepseek.com 或 OpenAI 兼容地址]
LLM_MODEL=[TODO: deepseek-chat / gpt-4o / ...]

# ---- 闲鱼认证 ----
XIANYU_COOKIE=[TODO: 闲鱼登录 Cookie]
XIANYU_TOKEN=[TODO: 如有]

# ---- 应用配置 ----
APP_ENV=development
LOG_LEVEL=INFO
REQUEST_TIMEOUT=60
MAX_SEARCH_RESULTS=50

# ---- [TODO: 补充其他环境变量] ----
```

---

## 十一、执行流程（时序图逻辑）

```
1. 用户在终端输入: "帮我看 iPhone 15 Pro 256G 二手性价比"
2. A2A Gateway 接收请求 → 创建 search_id → 返回 202 Accepted
3. Orchestrator Agent:
   a. 解析意图 → {product: "iPhone 15 Pro", spec: "256G"}
   b. 生成3个子任务，A和B并行启动
4. Finder Agent (Task A):
   a. 调用闲鱼 MCP search_items("iPhone 15 Pro 256G")
   b. 返回 TOP 20 二手列表
5. Encyclopedia Agent (Task B):
   a. 调用 scrapers 抓取京东/官网信息
   b. 提取新品价格和规格
   c. 写入 product_cache 表
6. 等 A 和 B 都完成后，Calculator Agent (Task C):
   a. 取新品最低价作为基准
   b. 对每个闲鱼商品计算折扣率、性价比分数
   c. 排序 → 生成推荐列表 + 综合结论
7. 结果写入 analysis_result → 通知 Gateway → 用户拉取结果
```

---

## 十二、待办清单 (依实现优先顺序)

- [ ] `[TODO]` 确定 AI Agent 框架（ADK / LangGraph / CrewAI）
- [ ] `[TODO]` 实现闲鱼 MCP Server（核心：搜索 + 详情）
- [ ] `[TODO]` 实现 Finder Agent + 调通 MCP 调用链路
- [ ] `[TODO]` 实现 Encyclopedia Agent + 至少一个数据源抓取
- [ ] `[TODO]` 实现 Calculator Agent + 性价比评分算法
- [ ] `[TODO]` 实现 Orchestrator 工作流编排
- [ ] `[TODO]` 搭建 FastAPI 网关 + A2A 协议适配
- [ ] `[TODO]` MySQL 表创建 + 数据层实现
- [ ] `[TODO]` Docker Compose 一键部署
- [ ] `[TODO]` 测试用例编写
- [ ] `[TODO]` 前端用户界面（Web UI / CLI）

---

## 十三、风险与注意事项

| 风险 | 说明 | 缓解方案 |
|------|------|----------|
| 闲鱼反爬 | 闲鱼对自动化请求可能有风控 | `[TODO: 如 使用官方API（如有）、控制频率、模拟正常行为]` |
| 网页抓取稳定性 | 京东/淘宝页面结构可能变化 | `[TODO: 如 多数据源容灾、定期更新选择器、监控告警]` |
| 价格时效性 | 二手商品价格经常变动 | `[TODO: 如 结果标注时效性、支持刷新]` |
| LLM 准确性 | LLM 可能理解偏差 | `[TODO: 如 Prompt 工程优化、结构化输出约束、人工审核入口]` |
| `[TODO]` | `[TODO]` | `[TODO]` |

---

> **下一步**：请将上面所有 `[TODO]` 标记替换为你的实际信息即可。如有任何模块需要深入细化，请告诉我！
