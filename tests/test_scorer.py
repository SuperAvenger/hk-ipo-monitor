from src.analyzer.scorer import _log_subscription, score_ipo


def test_score_ipo_accepts_numeric_strings():
    result = score_ipo(
        {
            "name": "Example AI",
            "industry": "人工智能",
            "entry_fee": "4999.50",
            "raw": {
                "subscription_multiple": "25.5",
                "fundraise": "8.2",
                "has_cornerstone": True,
            },
        }
    )

    assert result["phase"] == 2
    assert result["dimensions"]["subscription"] > 20
    assert 0 <= result["total"] <= 100
    assert result["confidence"]["level"] in {"medium", "high"}
    assert "subscription_data_unavailable" not in result["risk_flags"]


def test_score_ipo_degrades_invalid_numeric_values():
    result = score_ipo(
        {
            "name": "Example",
            "entry_fee": "N/A",
            "raw": {"subscription_multiple": "unknown", "fundraise": None},
        }
    )

    assert result["phase"] == 1
    assert result["dimensions"]["fundraise"] == 50
    assert result["dimensions"]["entry"] == 50
    assert result["confidence"]["level"] == "low"
    assert "subscription_data_unavailable" in result["risk_flags"]
    assert any(flag.startswith("missing_data:") for flag in result["risk_flags"])


def test_subscription_score_is_bounded():
    assert _log_subscription(-1) == 20
    assert _log_subscription("bad") == 20
    assert _log_subscription(10**20) == 98
