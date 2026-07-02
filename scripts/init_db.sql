-- ============================================================
-- catch_fish 数据库初始化脚本
-- MySQL 8.0+
-- 当 Docker 容器首次启动时自动执行
-- ============================================================

-- 创建数据库（如果不存在）
CREATE DATABASE IF NOT EXISTS catch_fish
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE catch_fish;

-- -----------------------------------------------------------
-- 1. 搜索记录表
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS search_log (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id    VARCHAR(64)  NOT NULL COMMENT '会话ID',
    user_query    TEXT         NOT NULL COMMENT '用户原始查询',
    parsed_intent JSON         COMMENT 'Orchestrator 解析后的意图JSON',
    status        ENUM('pending','processing','completed','failed') DEFAULT 'pending' COMMENT '任务状态',
    error_message TEXT         COMMENT '错误信息',
    created_at    DATETIME     DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at    DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_session (session_id),
    INDEX idx_status_created (status, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='搜索记录表';

-- -----------------------------------------------------------
-- 2. 闲鱼商品快照表
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS xianyu_items (
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
    INDEX idx_search (search_id),
    INDEX idx_price (price),
    CONSTRAINT fk_items_search FOREIGN KEY (search_id) REFERENCES search_log(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='闲鱼商品快照表';

-- -----------------------------------------------------------
-- 3. 商品百科缓存表
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS product_cache (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='商品百科缓存表';

-- -----------------------------------------------------------
-- 4. 性价比分析结果表
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS analysis_result (
    id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
    search_id           BIGINT NOT NULL COMMENT '关联 search_log.id',
    best_deal_item_id   BIGINT COMMENT '关联 xianyu_items.id（最佳选择）',
    new_price_baseline  DECIMAL(10,2) COMMENT '新品基准价格',
    avg_used_price      DECIMAL(10,2) COMMENT '二手均价',
    total_listings      INT    COMMENT '二手在售数量',
    recommendations     JSON   COMMENT '推荐列表JSON',
    market_summary      JSON   COMMENT '市场总结JSON',
    verdict_text        TEXT   COMMENT 'AI 分析结论',
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    UNIQUE KEY uk_search (search_id),
    INDEX idx_best_deal (best_deal_item_id),
    CONSTRAINT fk_analysis_search FOREIGN KEY (search_id) REFERENCES search_log(id) ON DELETE CASCADE,
    CONSTRAINT fk_analysis_item   FOREIGN KEY (best_deal_item_id) REFERENCES xianyu_items(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='性价比分析结果表';
