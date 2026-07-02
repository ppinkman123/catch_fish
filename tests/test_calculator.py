"""
Calculator Agent 单元测试
"""

import pytest

from src.agents.calculator.scoring import (
    calc_comprehensive_score,
    calc_discount_rate,
    normalize_condition,
    score_by_condition,
    score_by_discount,
    score_by_market,
    score_by_seller,
)


class TestDiscountRate:
    def test_half_price(self):
        assert calc_discount_rate(50, 100) == 0.5

    def test_full_price(self):
        assert calc_discount_rate(100, 100) == 1.0

    def test_zero_new_price(self):
        assert calc_discount_rate(50, 0) == 1.0


class TestScoreByDiscount:
    def test_very_cheap(self):
        score, comment = score_by_discount(0.3)
        assert score >= 35

    def test_moderate(self):
        score, comment = score_by_discount(0.65)
        assert 20 <= score <= 30

    def test_expensive(self):
        score, comment = score_by_discount(0.95)
        assert score < 10


class TestScoreByCondition:
    def test_like_new(self):
        score, _ = score_by_condition("like_new")
        assert score == 25

    def test_good(self):
        score, _ = score_by_condition("good")
        assert score == 16

    def test_unknown(self):
        score, _ = score_by_condition("random_text")
        assert score > 0


class TestScoreBySeller:
    def test_high_credit(self):
        score, _ = score_by_seller(820)
        assert score == 15

    def test_low_credit(self):
        score, _ = score_by_seller(550)
        assert score <= 5

    def test_none_credit(self):
        score, _ = score_by_seller(None)
        assert score > 0


class TestScoreByMarket:
    def test_abundant(self):
        score, _ = score_by_market(100)
        assert score == 10

    def test_scarce(self):
        score, _ = score_by_market(3)
        assert score <= 5


class TestNormalizeCondition:
    def test_new(self):
        assert normalize_condition("全新仅拆封") == "like_new"

    def test_99new(self):
        assert normalize_condition("99新") == "like_new"

    def test_good(self):
        assert normalize_condition("轻微划痕") == "good"

    def test_acceptable(self):
        assert normalize_condition("有磕碰") == "acceptable"


class TestComprehensiveScore:
    def test_great_deal(self):
        result = calc_comprehensive_score(
            used_price=5000,
            new_price=10000,
            condition="like_new",
            seller_credit=800,
            total_listings=50,
        )
        assert result["score"] >= 80
        assert result["discount_rate"] == 0.5
        assert result["savings"] == 5000

    def test_bad_deal(self):
        result = calc_comprehensive_score(
            used_price=9500,
            new_price=10000,
            condition="acceptable",
            seller_credit=500,
            total_listings=2,
        )
        assert result["score"] < 50

    def test_output_structure(self):
        result = calc_comprehensive_score(3000, 5000, "good", 700, 20)
        assert "score" in result
        assert "discount_rate" in result
        assert "savings" in result
        assert "details" in result
        assert "verdict_short" in result
        assert 0 <= result["score"] <= 100
