"""
性价比评分算法 — 定量计算模块
提供规则引擎辅助 LLM 做精确计算
"""

import math
from datetime import datetime, timezone


def calc_discount_rate(used_price: float, new_price: float) -> float:
    """计算折扣率 = 二手价 / 新品价"""
    if new_price <= 0:
        return 1.0
    return round(used_price / new_price, 4)


def score_by_discount(discount_rate: float) -> tuple[float, str]:
    """
    基于折扣率的评分（满分40分）

    返回: (得分, 评价)
    """
    if discount_rate <= 0.35:
        return (40, "价格极低，可能是捡漏价，但需确认真伪")
    elif discount_rate <= 0.50:
        return (38, "非常划算，比新品便宜一半以上")
    elif discount_rate <= 0.60:
        return (34, "比较划算")
    elif discount_rate <= 0.70:
        return (28, "有一定优惠")
    elif discount_rate <= 0.80:
        return (20, "优惠幅度一般")
    elif discount_rate <= 0.90:
        return (10, "优惠很小，不如买新品")
    else:
        return (0, "几乎没便宜，强烈建议买新品")


def score_by_condition(condition: str) -> tuple[float, str]:
    """
    基于成色的评分（满分25分）

    成色映射:
    - like_new / 全新 → 25
    - excellent / 几乎全新 → 22
    - good / 正常使用 → 16
    - acceptable / 有使用痕迹 → 8
    - poor → 3
    """
    mapping = {
        "like_new": (25, "全新/仅拆封"),
        "excellent": (22, "几乎全新"),
        "good": (16, "正常使用痕迹"),
        "acceptable": (8, "有较明显使用痕迹"),
        "poor": (3, "成色较差"),
    }
    key = condition.lower().replace("-", "_") if condition else "good"
    for k, v in mapping.items():
        if k in key:
            return v
    return (15, "成色未知")


def score_by_seller(credit_score: int | None) -> tuple[float, str]:
    """
    基于卖家信用的评分（满分15分）
    """
    if credit_score is None:
        return (8, "卖家信用未知")
    if credit_score >= 800:
        return (15, "信用极好")
    elif credit_score >= 700:
        return (12, "信用良好")
    elif credit_score >= 600:
        return (8, "信用一般")
    else:
        return (3, "信用偏低，需谨慎")


def score_by_market(total_listings: int) -> tuple[float, str]:
    """
    基于市场供需的评分（满分10分）
    """
    if total_listings >= 50:
        return (10, "供应充足，议价空间大")
    elif total_listings >= 20:
        return (7, "供应适中")
    elif total_listings >= 5:
        return (5, "供应偏少")
    else:
        return (3, "供应稀少，价格可能偏高")


def calc_depreciation_factor(release_date_str: str | None) -> float:
    """
    计算时间折旧系数
    数码产品一般第一年折旧最快（~30%），之后逐渐放缓

    返回: 折旧系数（1.0 = 全新，值越小表示折旧越大）
    """
    if not release_date_str:
        return 0.85  # 未知时保守估计

    try:
        release_date = datetime.fromisoformat(release_date_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        months = max(0, (now - release_date.replace(tzinfo=timezone.utc)).days / 30)

        if months <= 3:
            return 0.95
        elif months <= 6:
            return 0.90
        elif months <= 12:
            return 0.80
        elif months <= 24:
            return 0.65
        else:
            return 0.50
    except (ValueError, TypeError):
        return 0.85


def calc_comprehensive_score(
    used_price: float,
    new_price: float,
    condition: str,
    seller_credit: int | None,
    total_listings: int,
    release_date: str | None = None,
) -> dict:
    """
    综合性价比评分（加权计算 + 规则引擎）

    权重分配:
    - 折扣率: 40%
    - 成色: 25%
    - 卖家信用: 15%
    - 市场供需: 10%
    - 时间折旧: 10%

    返回:
        {
            "score": int,            # 0-100 综合评分
            "discount_rate": float,  # 折扣率
            "savings": float,        # 节省金额
            "details": {...},        # 各维度明细
            "verdict_short": str,    # 简短结论
        }
    """
    discount_rate = calc_discount_rate(used_price, new_price)
    savings = new_price - used_price

    s1, c1 = score_by_discount(discount_rate)
    s2, c2 = score_by_condition(condition)
    s3, c3 = score_by_seller(seller_credit)
    s4, c4 = score_by_market(total_listings)

    # 时间折旧因子转换为得分
    dep = calc_depreciation_factor(release_date)
    s5 = dep * 10
    c5 = f"已上市约{int((1-dep)*100/5)*5}个月" if dep < 1 else "近3个月新品"

    total_score = round(s1 + s2 + s3 + s4 + s5)

    if total_score >= 90:
        verdict_short = "强烈推荐👍"
    elif total_score >= 75:
        verdict_short = "推荐购买✅"
    elif total_score >= 60:
        verdict_short = "可以考虑🤔"
    elif total_score >= 40:
        verdict_short = "谨慎考虑⚠️"
    else:
        verdict_short = "建议买新品🆕"

    return {
        "score": total_score,
        "discount_rate": discount_rate,
        "savings": round(savings, 2),
        "details": {
            "discount": {"score": s1, "max": 40, "comment": c1},
            "condition": {"score": s2, "max": 25, "comment": c2},
            "seller": {"score": s3, "max": 15, "comment": c3},
            "market": {"score": s4, "max": 10, "comment": c4},
            "depreciation": {"score": round(s5, 1), "max": 10, "comment": c5},
        },
        "verdict_short": verdict_short,
    }


def normalize_condition(desc: str) -> str:
    """
    将各种成色描述标准化为统一枚举值

    示例:
        "99新" → "like_new"
        "仅拆封未使用" → "like_new"
        "正常使用一个月" → "excellent"
        "有轻微划痕" → "good"
    """
    desc_lower = desc.lower() if desc else ""

    if any(w in desc_lower for w in ["全新", "99新", "仅拆封", "未使用", "未拆封", "全新未激活"]):
        return "like_new"
    elif any(w in desc_lower for w in ["98新", "97新", "几乎全新", "一个月", "两周", "一周"]):
        return "excellent"
    elif any(w in desc_lower for w in ["95新", "9成新", "轻微", "小磕碰"]):
        return "good"
    elif any(w in desc_lower for w in ["9成", "8成", "划痕", "磕碰", "使用痕迹"]):
        return "acceptable"
    else:
        return "good"  # 默认
