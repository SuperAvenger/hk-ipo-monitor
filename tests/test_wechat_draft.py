from datetime import datetime

from src.publisher.wechat_draft import build_wechat_draft, save_wechat_draft


def sample_ipo():
    return {
        "code": "09999",
        "name": "示例科技",
        "industry": "人工智能",
        "entry_fee": 5050.5,
        "apply_deadline": "2026-06-30",
        "raw": {
            "price_range": "10.00-12.00 HKD",
            "lot_size": 500,
            "subscription_multiple": 42,
        },
    }


def sample_score():
    return {
        "total": 72,
        "recommendation": "谨慎申购",
        "dimensions": {"industry": 90, "valuation": 60},
        "confidence": {"level": "medium", "percent": 71},
        "risk_flags": ["high_entry_fee", "missing_data:cornerstone,fundraise"],
    }


def test_build_wechat_draft_contains_review_and_risk_sections():
    draft = build_wechat_draft(
        sample_ipo(),
        sample_score(),
        generated_at=datetime(2026, 6, 19, 9, 30),
    )

    assert "港股打新研究｜09999 示例科技" in draft
    assert "字段完整度 71%" in draft
    assert "入场费较高" in draft
    assert "部分字段缺失" in draft
    assert "不构成任何投资建议" in draft
    assert "自动发布" not in draft


def test_save_wechat_draft_uses_stable_reviewable_filename(tmp_path):
    path = save_wechat_draft(
        sample_ipo(),
        sample_score(),
        output_dir=tmp_path,
        generated_at=datetime(2026, 6, 19, 9, 30),
    )

    assert path.name == "2026-06-19-09999.md"
    assert path.read_text(encoding="utf-8").startswith("# 港股打新研究")
