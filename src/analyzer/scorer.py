"""
港股新股量化评分引擎 v2 - 基于 142 只历史数据回测校准
支持 Phase 1 (刚发售, 无认购倍数) 和 Phase 2 (认购期, 有认购倍数)

核心发现:
  - 认购倍数(log) 是最强预测因子 (r=0.63), 但仅 Phase 2 可用
  - 行业景气度 第二重要 (r=0.37), Phase 1 可用
  - 基石投资者 有帮助 (r=0.12), Phase 1 可用
  - 募资额 影响较小 (r=0.07), Phase 1 可用
"""
import logging
import math
from typing import Optional

logger = logging.getLogger(__name__)


def _positive_float(value, default: float = 0.0) -> float:
    """Convert scraper values to a positive float without breaking a monitor run."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) and number > 0 else default


# 行业景气度评分 (基于 2024-2026 年港股 IPO 首日涨幅统计)
INDUSTRY_SCORES = {
    "AI": 95, "医疗AI": 95, "人工智能": 95,
    "自动驾驶": 85, "半导体": 85, "芯片": 85,
    "医药": 75, "生物": 75, "创新药": 75,
    "新能源": 72, "光伏": 72, "锂电": 72,
    "机器人": 70, "智能制造": 70,
    "科技": 65, "软件": 65, "SaaS": 65,
    "消费": 60, "餐饮": 60, "零售": 60,
    "制造": 55, "工业": 55,
    "资源": 55, "矿业": 55,
    "医疗": 50, "医疗保健": 50, "医疗器械": 50,
    "物流": 45, "供应链": 45,
    "材料": 45, "化工": 45,
    "服务": 40, "物业": 40,
    "金融": 40, "保险": 40, "银行": 40,
    "汽车": 50, "文旅": 35, "农业": 40,
    "建筑": 35, "房地产": 30,
}

INDUSTRY_KEYWORDS = {
    "AI": ["人工智能", "AI", "机器学习", "深度学习", "大模型", "智能"],
    "半导体": ["半导体", "芯片", "集成电路", "晶圆"],
    "自动驾驶": ["自动驾驶", "无人驾驶", "激光雷达", "ADAS"],
    "医药": ["医药", "生物", "制药", "创新药", "基因"],
    "机器人": ["机器人", "自动化", "工业机器人"],
    "新能源": ["新能源", "光伏", "锂电", "储能", "风电"],
    "消费": ["消费", "餐饮", "零售", "食品", "饮料", "茶"],
    "科技": ["科技", "软件", "互联网", "云计算", "大数据"],
    "制造": ["制造", "工业", "机械", "电子"],
    "医疗": ["医疗", "健康", "医院", "诊断"],
}


def _match_industry(ipo: dict) -> int:
    """匹配行业景气度评分"""
    raw = ipo.get("raw", ipo)
    industry = ipo.get("industry", "")
    category = raw.get("category", "")
    name = ipo.get("name", "")
    combined = f"{industry} {category} {name}"

    for key, score in INDUSTRY_SCORES.items():
        if key in combined:
            return score

    for industry_type, keywords in INDUSTRY_KEYWORDS.items():
        for kw in keywords:
            if kw in combined:
                return INDUSTRY_SCORES.get(industry_type, 50)

    return 50


def _log_subscription(mult) -> float:
    """认购倍数对数化 (0-100 分)"""
    mult = _positive_float(mult)
    if not mult:
        return 20
    score = 20 + 10.5 * math.log(mult)
    return min(98, max(5, score))


def _build_assessment(ipo: dict, raw: dict, phase: int) -> tuple[dict, list[str]]:
    """Describe data completeness and risks so the score is not read as false precision."""
    checks = {
        "industry": bool(ipo.get("industry") or raw.get("category")),
        "cornerstone": "has_cornerstone" in raw or bool(raw.get("cornerstone")),
        "fundraise": _positive_float(raw.get("fundraise")) > 0,
        "valuation": bool(raw.get("price_range") or ipo.get("price_range")),
        "entry_fee": _positive_float(ipo.get("entry_fee")) > 0,
        "18c_status": "is_18c" in raw,
        "subscription": _positive_float(raw.get("subscription_multiple")) > 0,
    }
    known = sum(checks.values())
    percent = round(known / len(checks) * 100)
    if percent >= 75:
        label = "high"
    elif percent >= 50:
        label = "medium"
    else:
        label = "low"

    risk_flags = []
    if phase == 1:
        risk_flags.append("subscription_data_unavailable")
    if raw.get("is_18c") is True:
        risk_flags.append("chapter_18c_company")
    if _positive_float(ipo.get("entry_fee")) >= 10000:
        risk_flags.append("high_entry_fee")
    missing = [name for name, available in checks.items() if not available]
    if missing:
        risk_flags.append("missing_data:" + ",".join(missing))

    return {
        "level": label,
        "percent": percent,
        "known_fields": known,
        "total_fields": len(checks),
    }, risk_flags


def score_ipo(ipo: dict) -> dict:
    """
    对一只新股进行量化评分 (v2 回测校准版)
    支持 Phase 1 (无认购倍数) 和 Phase 2 (有认购倍数)

    Phase 1: 刚发售时, 靠行业/基石/募资/入场费判断 → 决定是否打新
    Phase 2: 认购期, 有认购倍数后更新评分 → 确认/调整策略
    """
    raw = ipo.get("raw", ipo)

    dims = {}
    mult = _positive_float(raw.get("subscription_multiple"))
    has_mult = mult > 0

    # ── 共用维度 (Phase 1 & 2 都可用) ──

    # 行业景气度 (回测 r=0.37)
    dims["industry"] = _match_industry(ipo)

    # 基石投资者 (回测 r=0.12)
    has_cornerstone = raw.get("has_cornerstone", False)
    if has_cornerstone:
        dims["cornerstone"] = 80
    else:
        cornerstone = raw.get("cornerstone", "")
        dims["cornerstone"] = 80 if cornerstone else 35

    # 募资规模 (回测 r=0.07)
    fundraise = _positive_float(raw.get("fundraise"))
    if fundraise:
        dims["fundraise"] = min(90, max(20, 30 + 20 * math.log10(max(0.1, fundraise))))
    else:
        dims["fundraise"] = 50

    # 估值定价
    price_range = raw.get("price_range", "")
    if price_range and price_range != "N/A":
        dims["valuation"] = 55
    else:
        dims["valuation"] = 40

    # 入场门槛
    entry_fee = _positive_float(ipo.get("entry_fee"))
    if entry_fee:
        if entry_fee < 3000:
            dims["entry"] = 75
        elif entry_fee < 6000:
            dims["entry"] = 60
        elif entry_fee < 10000:
            dims["entry"] = 45
        else:
            dims["entry"] = 30
    else:
        dims["entry"] = 50

    # 18C 风险
    is_18c = raw.get("is_18c", False)
    dims["risk_18c"] = 35 if is_18c else 65

    # ── Phase 判断 & 权重分配 ──
    if has_mult:
        # Phase 2: 有认购倍数, 最完整评分
        dims["subscription"] = _log_subscription(mult)
        phase = 2
        weights = {
            "subscription": 0.35,
            "industry": 0.25,
            "cornerstone": 0.12,
            "fundraise": 0.08,
            "valuation": 0.08,
            "entry": 0.07,
            "risk_18c": 0.05,
        }
    else:
        # Phase 1: 无认购倍数, 权重重新分配
        phase = 1
        weights = {
            "industry": 0.35,
            "cornerstone": 0.20,
            "fundraise": 0.15,
            "valuation": 0.12,
            "entry": 0.10,
            "risk_18c": 0.08,
        }

    total = sum(dims.get(k, 50) * weights[k] for k in weights)
    total = round(total, 1)

    # 推荐等级
    if phase == 1:
        # Phase 1 阈值更保守
        if total >= 72:
            rec = "🔴 强烈申购"
        elif total >= 58:
            rec = "🟠 建议申购"
        elif total >= 45:
            rec = "🟡 观望"
        else:
            rec = "⚫ 建议回避"
    else:
        if total >= 80:
            rec = "🔴 强烈申购"
        elif total >= 65:
            rec = "🟠 建议申购"
        elif total >= 50:
            rec = "🟡 观望"
        else:
            rec = "⚫ 建议回避"

    # 生成详情
    dim_labels = {
        "subscription": "认购热度",
        "industry": "行业景气",
        "cornerstone": "基石投资",
        "fundraise": "募资规模",
        "valuation": "估值定价",
        "entry": "入场门槛",
        "risk_18c": "18C风险",
    }

    detail_lines = []
    for k, v in sorted(dims.items(), key=lambda x: -x[1]):
        bar = "█" * int(v / 10) + "░" * (10 - int(v / 10))
        label = dim_labels.get(k, k)
        detail_lines.append(f"{label}: {bar} {v:.0f}")

    confidence, risk_flags = _build_assessment(ipo, raw, phase)
    return {
        "total": total,
        "dimensions": dims,
        "recommendation": rec,
        "detail": "\n".join(detail_lines),
        "phase": phase,
        "confidence": confidence,
        "risk_flags": risk_flags,
    }


def predict_first_day_return(score: dict, ipo: dict) -> str:
    """基于评分预测首日涨幅区间"""
    total = score["total"]
    phase = score.get("phase", 1)
    if phase == 1:
        if total >= 72:
            return "+20%~+80%"
        elif total >= 58:
            return "+5%~+30%"
        elif total >= 45:
            return "-10%~+15%"
        else:
            return "-30%~0%"
    else:
        if total >= 80:
            return "+30%~+100%"
        elif total >= 65:
            return "+10%~+50%"
        elif total >= 50:
            return "-5%~+20%"
        else:
            return "-30%~+5%"


def _dim_label(key: str) -> str:
    labels = {
        "subscription": "认购热度",
        "industry": "行业景气",
        "cornerstone": "基石投资",
        "fundraise": "募资规模",
        "valuation": "估值定价",
        "entry": "入场门槛",
        "risk_18c": "18C风险",
    }
    return labels.get(key, key)
