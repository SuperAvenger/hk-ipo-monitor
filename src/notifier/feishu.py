"""
飞书 Webhook 推送 - 交互卡片消息
"""
import json
import logging
import os
from typing import Optional

import requests

logger = logging.getLogger(__name__)


def _get_webhook() -> str:
    return os.environ.get("FEISHU_WEBHOOK", "")


def send_card(title: str, content: str, color: str = "blue",
              button_text: str = "", button_url: str = "") -> bool:
    """
    发送飞书交互卡片。
    color: blue/green/orange/red/purple
    """
    webhook = _get_webhook()
    if not webhook:
        logger.warning("FEISHU_WEBHOOK not set, skip sending")
        return False

    elements = [
        {
            "tag": "div",
            "text": {"tag": "lark_md", "content": content}
        }
    ]

    if button_text and button_url:
        elements.append({
            "tag": "action",
            "actions": [{
                "tag": "button",
                "text": {"tag": "plain_text", "content": button_text},
                "type": "primary",
                "url": button_url,
            }]
        })

    card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": color,
            },
            "elements": elements,
        }
    }

    try:
        resp = requests.post(webhook, json=card, timeout=10)
        result = resp.json()
        if result.get("code") == 0 or result.get("StatusCode") == 0:
            logger.info(f"Feishu sent: {title}")
            return True
        else:
            logger.error(f"Feishu error: {result}")
            return False
    except Exception as e:
        logger.error(f"Feishu send failed: {e}")
        return False


# ── 业务消息模板 ─────────────────────────────────────────────

def _first_value(*values, default=""):
    for value in values:
        if value not in (None, "", "N/A", "?"):
            return value
    return default


def _fmt_money(value, currency="HKD") -> str:
    if value in (None, "", "N/A", "?"):
        return ""
    try:
        return f"{float(value):,.0f} {currency}"
    except (TypeError, ValueError):
        return str(value)


def _company_profile_line(ipo: dict) -> str:
    raw = ipo.get("raw", ipo)
    industry = _first_value(ipo.get("industry"), raw.get("industry"), raw.get("category"))
    source = _first_value(ipo.get("source"), raw.get("source"))
    bits = []
    if industry:
        bits.append(f"行业/赛道：{industry}")
    if source:
        bits.append(f"数据源：{source}")
    if ipo.get("hkex_docs"):
        bits.append(f"港交所文件：{len(ipo['hkex_docs'])} 份")
    return "；".join(bits) if bits else "公司业务信息待补充，先按招股数据和量化评分跟踪。"


def _valuation_line(ipo: dict) -> str:
    raw = ipo.get("raw", ipo)
    ah_discount = _first_value(
        ipo.get("ah_discount"),
        ipo.get("discount"),
        raw.get("ah_discount"),
        raw.get("discount"),
    )
    a_price = _first_value(ipo.get("a_share_price"), raw.get("a_share_price"))
    h_price = _first_value(ipo.get("h_share_price"), raw.get("h_share_price"))
    if ah_discount:
        return f"A/H 折价：{ah_discount}"
    if a_price and h_price:
        return f"A股价：{a_price}；H股发行价：{h_price}"
    return "A/H 折价暂无结构化数据，需人工结合 A 股收盘价和发行价复核。"


def _issue_line(ipo: dict) -> str:
    raw = ipo.get("raw", ipo)
    price = _first_value(raw.get("price_range"), ipo.get("price_range"), raw.get("ipo_price"))
    lot = _first_value(raw.get("lot_size"), ipo.get("lot_size"))
    fee = _first_value(ipo.get("entry_fee"), raw.get("entry_fee"))
    fundraise = _first_value(raw.get("fundraise"), ipo.get("fundraise"))
    parts = []
    if price:
        parts.append(f"招股价：{price} HKD")
    if lot:
        parts.append(f"每手：{lot} 股")
    if fee:
        parts.append(f"入场费：{_fmt_money(fee)}")
    if fundraise:
        parts.append(f"募资额：{fundraise}")
    return "；".join(parts) if parts else "发行规模、每手和入场费待补充。"


def _cornerstone_line(ipo: dict) -> str:
    raw = ipo.get("raw", ipo)
    cornerstone = _first_value(raw.get("cornerstone"), ipo.get("cornerstone"))
    greenshoe = _first_value(raw.get("greenshoe"), ipo.get("greenshoe"), raw.get("green_shoe"))
    sponsor = _first_value(raw.get("sponsor"), ipo.get("sponsor"), raw.get("underwriter"))
    parts = []
    if cornerstone:
        parts.append(f"基石：{cornerstone}")
    else:
        parts.append("基石：待补充")
    if greenshoe:
        parts.append(f"绿鞋：{greenshoe}")
    if sponsor:
        parts.append(f"保荐人/承销：{sponsor}")
    return "；".join(parts)


def _financial_line(ipo: dict) -> str:
    raw = ipo.get("raw", ipo)
    revenue = _first_value(raw.get("revenue"), ipo.get("revenue"))
    gross_profit = _first_value(raw.get("gross_profit"), ipo.get("gross_profit"))
    gross_margin = _first_value(raw.get("gross_margin"), ipo.get("gross_margin"))
    profit = _first_value(raw.get("profit"), ipo.get("profit"), raw.get("net_profit"))
    parts = []
    if revenue:
        parts.append(f"营收：{revenue}")
    if gross_profit:
        parts.append(f"毛利：{gross_profit}")
    if gross_margin:
        parts.append(f"毛利率：{gross_margin}")
    if profit:
        parts.append(f"净利润：{profit}")
    return "；".join(parts) if parts else "财务数据暂无结构化抓取，需看招股书补充营收、毛利、利润趋势。"


def _allocation_line(ipo: dict) -> str:
    raw = ipo.get("raw", ipo)
    public_lots = _first_value(raw.get("public_lots"), ipo.get("public_lots"))
    group_a_tail = _first_value(raw.get("group_a_tail"), ipo.get("group_a_tail"))
    group_b_head = _first_value(raw.get("group_b_head"), ipo.get("group_b_head"))
    subscription = _first_value(raw.get("subscription_multiple"), ipo.get("subscription_multiple"))
    parts = []
    if public_lots:
        parts.append(f"公开发售手数：{public_lots}")
    if group_a_tail:
        parts.append(f"甲尾：{group_a_tail}")
    if group_b_head:
        parts.append(f"乙头：{group_b_head}")
    if subscription:
        parts.append(f"认购倍数：{subscription} 倍")
    return "；".join(parts) if parts else "甲乙组和中签率数据待补充；当前先按公开资料和认购热度判断。"


def _conclusion_line(score: dict, ai_analysis: dict | None) -> str:
    rec = score.get("recommendation", "")
    total = score.get("total", 0)
    if ai_analysis:
        strategy = ai_analysis.get("strategy") or ai_analysis.get("summary")
        if strategy:
            return f"{rec}，量化评分 {total}/100。{strategy}"
    return f"{rec}，量化评分 {total}/100。若估值折价不足或基本面一般，倾向少打/不打；若认购热度明显升温再复核。"


def push_new_ipo(ipo: dict, score: dict, ai_analysis: dict = None) -> bool:
    """新股出现通知 — 招股开始时推送，打新决策用"""
    code = ipo.get("code", "")
    name = ipo.get("name", "")
    total = score["total"]
    rec = score["recommendation"]
    pred = ipo.get("predicted_return", "")

    # 判断是否还在招股期
    deadline = ipo.get("apply_deadline", "")
    is_open = True
    if deadline:
        try:
            from datetime import datetime
            dl = datetime.strptime(deadline.replace("/", "-"), "%Y-%m-%d")
            is_open = dl.date() >= datetime.now().date()
        except (ValueError, TypeError):
            pass

    status_emoji = "🟢 招股中" if is_open else "🔴 已截止"
    raw = ipo.get("raw", ipo)

    content = (
        f"**{code} {name}**  {status_emoji}\n\n"
        f"❶ **公司信息**\n{_company_profile_line(ipo)}\n\n"
        f"❷ **估值 / A-H 折价**\n{_valuation_line(ipo)}\n\n"
        f"❸ **发行信息**\n{_issue_line(ipo)}\n\n"
        f"❹ **基石、绿鞋与保荐人**\n{_cornerstone_line(ipo)}\n\n"
        f"❺ **公司财务信息**\n{_financial_line(ipo)}\n\n"
        f"❻ **中签率 / 认购热度**\n{_allocation_line(ipo)}\n\n"
    )

    list_date = raw.get("listing_date") or ipo.get("listing_date", "")
    grey = ipo.get("grey_market_date") or raw.get("grey_market_date")
    if deadline or grey or list_date:
        content += "📅 **关键日期**\n"
        if deadline:
            content += f"招股截止：**{deadline}**\n"
        if grey:
            content += f"暗盘：**{grey}**\n"
        if list_date:
            content += f"上市日：**{list_date}**\n"
        content += "\n"

    if pred:
        content += f"📈 **预测首日：{pred}**\n\n"

    # AI 分析结果
    if ai_analysis:
        rating = ai_analysis.get("rating", "")
        summary = ai_analysis.get("summary", "")
        confidence = ai_analysis.get("confidence", 0)
        strategy = ai_analysis.get("strategy", "")
        first_day = ai_analysis.get("first_day_guess", "")

        # 评级颜色
        rating_map = {
            "强烈推荐": "🔴", "推荐": "🟠", "谨慎推荐": "🟡",
            "中性": "⚪", "不推荐": "⚫"
        }
        rating_icon = rating_map.get(rating, "⚪")

        content += f"🤖 **AI 观点**\n"
        content += f"{rating_icon} **{rating}** (信心度: {confidence}/10)\n"
        if summary:
            content += f"{summary}\n"
        if first_day:
            content += f"首日判断：**{first_day}**\n"

        # 优势
        pros = ai_analysis.get("pros", [])
        if pros:
            content += "\n利好：\n"
            for p in pros[:3]:
                content += f"- {p}\n"

        # 风险
        cons = ai_analysis.get("cons", [])
        if cons:
            content += "\n风险：\n"
            for c in cons[:3]:
                content += f"- {c}\n"

    content += f"\n❼ **总结**\n{_conclusion_line(score, ai_analysis)}\n"

    fee = _first_value(ipo.get("entry_fee"), raw.get("entry_fee"))
    if fee:
        try:
            content += f"\n💡 10倍杠杆参考：约 **{float(fee) * 10:,.0f} HKD** 融资额度\n"
        except (TypeError, ValueError):
            pass

    # 维度评分
    content += "\n**量化维度:**\n"
    dims = score["dimensions"]
    for k in sorted(dims, key=dims.get, reverse=True)[:5]:
        from analyzer.scorer import _dim_label
        bar = "█" * int(dims[k] / 10) + "░" * (10 - int(dims[k] / 10))
        content += f"{_dim_label(k)}：{bar} {dims[k]:.0f}\n"

    # 详情按钮
    detail_url = f"http://www.aastocks.com/sc/stocks/market/ipo/upcomingipo/company-summary?symbol={code}"

    return send_card(
        title=f"🆕 港股新股速报 — {code} {name}",
        content=content,
        color="blue" if is_open else "gray",
        button_text="📋 查看招股书" if is_open else "",
        button_url=detail_url if is_open else "",
    )


def push_subscription_update(ipo: dict, old_mult: float, new_mult: float) -> bool:
    """认购倍数跳档通知"""
    code = ipo.get("code", "")
    name = ipo.get("name", "")

    # 判断热度级别
    if new_mult >= 1000:
        heat = "🔥🔥🔥 超级热门"
    elif new_mult >= 500:
        heat = "🔥🔥 非常热门"
    elif new_mult >= 100:
        heat = "🔥 热门"
    else:
        heat = "📈 升温"

    content = (
        f"**{code} {name}**\n\n"
        f"认购倍数变化: **{old_mult:.0f}倍 → {new_mult:.0f}倍**\n"
        f"热度: {heat}\n"
    )

    return send_card(
        title=f"📊 认购热度更新 — {code}",
        content=content,
        color="orange",
    )


def push_score_report(ipo: dict, score: dict) -> bool:
    """最终评分报告 (截止前推送)"""
    code = ipo.get("code", "")
    name = ipo.get("name", "")
    total = score["total"]
    rec = score["recommendation"]
    pred = ipo.get("predicted_return", "")

    content = (
        f"**{code} {name}**\n\n"
        f"━━━━ 评分报告 ━━━━\n"
        f"📊 综合评分: **{total}/100**\n"
        f"🎯 建议: **{rec}**\n"
        f"📈 预测首日: **{pred}**\n\n"
        f"**全维度评分:**\n{score['detail']}\n"
    )

    return send_card(
        title=f"🎯 打新建议 — {code} ({rec})",
        content=content,
        color="green" if total >= 65 else "red",
    )


def push_dark_pool(ipo: dict, dark_data: dict, score: dict) -> bool:
    """暗盘表现通知"""
    code = ipo.get("code", "")
    name = ipo.get("name", "")
    pct = dark_data.get("percent", 0)
    price = dark_data.get("current", 0)

    if pct > 10:
        emoji = "🚀"
        msg = "暗盘大涨，情绪乐观"
    elif pct > 0:
        emoji = "📈"
        msg = "暗盘上涨，符合预期"
    elif pct > -5:
        emoji = "📉"
        msg = "暗盘小跌，关注修正机会"
    else:
        emoji = "💥"
        msg = "暗盘大跌，谨慎对待"

    content = (
        f"**{code} {name}**\n\n"
        f"{emoji} 暗盘: **{price} HKD** ({pct:+.1f}%)\n"
        f"💡 {msg}\n"
    )

    return send_card(
        title=f"🌙 暗盘播报 — {code}",
        content=content,
        color="green" if pct >= 0 else "red",
    )


def push_error(msg: str) -> bool:
    """错误通知"""
    return send_card(
        title="⚠️ 港股打新监控异常",
        content=msg,
        color="red",
    )


def push_hot_ipo(ipo: dict, mult: float) -> bool:
    """热门追加推送 — 认购超 500 倍时"""
    code = ipo.get("code", "")
    name = ipo.get("name", "")

    if mult >= 3000:
        heat = "🔥🔥🔥 超级热门"
    elif mult >= 1000:
        heat = "🔥🔥 非常热门"
    else:
        heat = "🔥 热门"

    content = (
        f"**{code} {name}**\n\n"
        f"认购倍数: **{mult:,.0f} 倍** {heat}\n\n"
        f"市场情绪非常积极，建议重点关注！\n"
    )

    fee = ipo.get("entry_fee", 0)
    if fee:
        content += f"\n🎫 入场费: **{fee:,.0f}** HKD"
        content += f"\n💡 10 倍杠杆: 约 **{fee * 10:,.0f}** HKD"

    deadline = ipo.get("apply_deadline", "")
    if deadline:
        content += f"\n⏰ 截止: **{deadline}**"

    return send_card(
        title=f"🔥 热门新股 — {code} {name} ({mult:,.0f}倍)",
        content=content,
        color="red",
    )
