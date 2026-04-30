"""
港股新股量化评分引擎 - 11 维度
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def score_ipo(ipo: dict) -> dict:
    """
    对一只新股进行 11 维度量化评分。
    输入: ipo dict (来自 scraper)
    输出: {"total": float, "dimensions": {...}, "recommendation": str, "detail": str}
    """
    dims = {}
    raw = ipo.get("raw", ipo)

    # 1. 估值定价 (18%)
    dims["valuation"] = _score_valuation(raw)

    # 2. 认购热度 (15%)
    dims["subscription"] = _score_subscription(raw)

    # 3. 财务状况 (14%)
    dims["financial"] = _score_financial(raw)

    # 4. 行业竞争 (10%)
    dims["industry"] = _score_industry(raw)

    # 5. 基石投资者 (10%)
    dims["cornerstone"] = _score_cornerstone(raw)

    # 6. 公司基本面 (8%)
    dims["fundamentals"] = _score_fundamentals(raw)

    # 7. 承销发行 (8%)
    dims["underwriter"] = _score_underwriter(raw)

    # 8. 上市后流动性 (7%)
    dims["liquidity"] = _score_liquidity(raw)

    # 9. 绿鞋机制 (5%)
    dims["greenshoe"] = _score_greenshoe(raw)

    # 10. 股东构成 (3%)
    dims["shareholders"] = _score_shareholders(raw)

    # 11. 法律诉讼 (2%)
    dims["legal"] = _score_legal(raw)

    weights = {
        "valuation": 0.18, "subscription": 0.15, "financial": 0.14,
        "industry": 0.10, "cornerstone": 0.10, "fundamentals": 0.08,
        "underwriter": 0.08, "liquidity": 0.07, "greenshoe": 0.05,
        "shareholders": 0.03, "legal": 0.02,
    }

    total = sum(dims[k] * weights[k] for k in weights)
    total = round(total, 1)

    # 推荐等级
    if total >= 75:
        rec = "🟢 强烈申购"
    elif total >= 65:
        rec = "🟡 建议申购"
    elif total >= 55:
        rec = "🟠 观望"
    else:
        rec = "🔴 建议回避"

    # 生成详情文本
    detail_lines = []
    for k, v in sorted(dims.items(), key=lambda x: -x[1]):
        bar = "█" * int(v / 10) + "░" * (10 - int(v / 10))
        label = _dim_label(k)
        detail_lines.append(f"{label}: {bar} {v:.0f}")

    return {
        "total": total,
        "dimensions": dims,
        "recommendation": rec,
        "detail": "\n".join(detail_lines),
    }


def _dim_label(key: str) -> str:
    labels = {
        "valuation": "估值定价", "subscription": "认购热度", "financial": "财务状况",
        "industry": "行业竞争", "cornerstone": "基石投资", "fundamentals": "基本面",
        "underwriter": "承销发行", "liquidity": "流动性", "greenshoe": "绿鞋",
        "shareholders": "股东构成", "legal": "法律风险",
    }
    return labels.get(key, key)


# ── 各维度评分函数 (0-100) ────────────────────────────────────

def _score_valuation(raw: dict) -> float:
    """估值定价: 基于招股价与行业中位数对比"""
    # 简化逻辑: 有数据时做 PE/PB 对比，无数据给默认分
    pe = raw.get("pe_ratio")
    industry_pe = raw.get("industry_pe")
    if pe and industry_pe and industry_pe > 0:
        ratio = pe / industry_pe
        if ratio < 0.7:
            return 90  # 低估
        elif ratio < 1.0:
            return 75
        elif ratio < 1.3:
            return 60
        elif ratio < 2.0:
            return 40
        else:
            return 25  # 高估
    # 无数据: 根据是否有价格区间给模糊分
    price_range = raw.get("price_range", "")
    if price_range and "-" in str(price_range):
        return 60  # 有价格区间，默认中性
    return 55


def _score_subscription(raw: dict) -> float:
    """认购热度: 基于公开发售认购倍数"""
    mult = raw.get("subscription_multiple") or raw.get("over_subscribe_rate") or 0
    if mult <= 0:
        return 50  # 尚未开始/无数据
    if mult >= 3000:
        return 95
    elif mult >= 1000:
        return 88
    elif mult >= 500:
        return 80
    elif mult >= 100:
        return 72
    elif mult >= 50:
        return 65
    elif mult >= 10:
        return 55
    else:
        return 40  # 认购不足


def _score_financial(raw: dict) -> float:
    """财务状况: 营收增长、利润率、负债率"""
    rev_growth = raw.get("revenue_growth")
    profit_margin = raw.get("profit_margin")
    score = 55  # 基准分
    if rev_growth is not None:
        if rev_growth > 50:
            score += 20
        elif rev_growth > 20:
            score += 12
        elif rev_growth > 0:
            score += 5
        else:
            score -= 10
    if profit_margin is not None:
        if profit_margin > 20:
            score += 15
        elif profit_margin > 10:
            score += 8
        elif profit_margin > 0:
            score += 3
        else:
            score -= 10  # 亏损
    return max(10, min(100, score))


def _score_industry(raw: dict) -> float:
    """行业竞争: 热门行业加分"""
    industry = (raw.get("industry") or "").lower()
    hot_keywords = ["科技", "ai", "人工智能", "半导体", "新能源", "医疗", "生物",
                    "technology", "semiconductor", "biotech", "new energy"]
    cold_keywords = ["地产", "建筑", "传统制造", "纺织", "real estate", "construction"]

    if any(kw in industry for kw in hot_keywords):
        return 80
    elif any(kw in industry for kw in cold_keywords):
        return 35
    return 60


def _score_cornerstone(raw: dict) -> float:
    """基石投资者: 有名气大、占比高加分"""
    cornerstone = raw.get("cornerstone") or raw.get("cornerstone_investor") or ""
    if not cornerstone:
        return 40  # 无基石
    # 简化: 有基石就加分，知名机构额外加分
    base = 60
    big_names = ["高瓴", "中投", "淡马锡", "GIC", "黑石", "红杉", "腾讯",
                 "阿里", "美团", "小米", "Temasek", "BlackRock", "Sequoia"]
    name_str = str(cornerstone)
    for name in big_names:
        if name.lower() in name_str.lower():
            base += 10
            break
    return min(95, base)


def _score_fundamentals(raw: dict) -> float:
    """公司基本面: 募资规模、公司历史"""
    fundraise = raw.get("fundraise") or raw.get("fund_raising_amount") or 0
    if fundraise > 100:  # 亿港元
        return 80
    elif fundraise > 50:
        return 72
    elif fundraise > 10:
        return 65
    elif fundraise > 0:
        return 55
    return 55


def _score_underwriter(raw: dict) -> float:
    """承销发行: 大投行加分"""
    underwriters = raw.get("underwriter") or raw.get("sponsors") or ""
    big_banks = ["高盛", "摩根", "中金", "中信", "大摩", "小摩", "花旗",
                 "Goldman", "Morgan Stanley", "CICC", "CITIC", "JPMorgan", "Citi"]
    u_str = str(underwriters)
    count = sum(1 for b in big_banks if b.lower() in u_str.lower())
    if count >= 2:
        return 85
    elif count == 1:
        return 72
    return 55


def _score_liquidity(raw: dict) -> float:
    """上市后流动性: 基于募资规模和lot_size"""
    lot_size = raw.get("lot_size") or 0
    fundraise = raw.get("fundraise") or raw.get("fund_raising_amount") or 0
    score = 55
    if fundraise > 50:
        score += 15
    if lot_size and lot_size <= 500:
        score += 10  # 小手数，散户友好
    return min(90, score)


def _score_greenshoe(raw: dict) -> float:
    """绿鞋机制: 有绿鞋加分"""
    greenshoe = raw.get("greenshoe") or raw.get("over_allotment")
    if greenshoe:
        return 75
    return 45


def _score_shareholders(raw: dict) -> float:
    """股东构成: 老股发售比例"""
    old_share = raw.get("old_share_ratio") or 0
    if old_share > 50:
        return 35  # 大比例老股发售，信号不好
    elif old_share > 20:
        return 55
    return 65


def _score_legal(raw: dict) -> float:
    """法律诉讼: 有无重大诉讼"""
    legal = raw.get("legal_risk") or raw.get("litigation")
    if legal:
        return 30
    return 70  # 默认无风险


# ── 预测首日涨幅 ─────────────────────────────────────────────

def predict_first_day_return(score: dict, ipo: dict) -> str:
    """基于评分和认购倍数，预测首日涨幅区间"""
    total = score["total"]
    mult = ipo.get("raw", ipo).get("subscription_multiple") or 0

    if total >= 75 and mult >= 500:
        return "+20% ~ +40%"
    elif total >= 75 and mult >= 100:
        return "+10% ~ +25%"
    elif total >= 65 and mult >= 100:
        return "+5% ~ +15%"
    elif total >= 65:
        return "0% ~ +10%"
    elif total >= 55:
        return "-5% ~ +5%"
    else:
        return "-15% ~ -5%"
