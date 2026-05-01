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

def push_new_ipo(ipo: dict, score: dict, ai_analysis: dict = None):
    """新股出现通知 — 招股开始时推送，打新决策用"""
    code = ipo.get("code", "")
    name = ipo.get("name", "")
    total = score["total"]
    rec = score["recommendation"]
    pred = ipo.get("predicted_return", "")

    # 评分星星
    stars = "⭐" * min(5, int(total / 20))

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

    content = (
        f"**{code} {name}**  {status_emoji}\n\n"
        f"📊 综合评分: **{total}/100** {stars}"
        f"  (Phase {score.get('phase', 1)})\n"
        f"🎯 量化建议: **{rec}**\n"
    )

    if pred:
        content += f"📈 预测首日: **{pred}**\n"

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

        content += f"\n━━━ 🤖 AI 分析 ━━━\n"
        content += f"{rating_icon} **{rating}** (信心度: {confidence}/10)\n"
        if summary:
            content += f"💬 {summary}\n"
        if first_day:
            content += f"📊 首日预测: **{first_day}**\n"
        if strategy:
            content += f"🎯 策略: {strategy}\n"

        # 优势
        pros = ai_analysis.get("pros", [])
        if pros:
            content += "\n**✅ 利好:**\n"
            for p in pros[:3]:
                content += f"  • {p}\n"

        # 风险
        cons = ai_analysis.get("cons", [])
        if cons:
            content += "\n**⚠️ 风险:**\n"
            for c in cons[:3]:
                content += f"  • {c}\n"

    content += "\n━━━ 打新关键信息 ━━━\n"

    # 关键打新信息
    raw = ipo.get("raw", ipo)
    price = raw.get("price_range") or ipo.get("price_range", "")
    if price:
        content += f"💰 招股价: **{price}** HKD\n"

    lot = raw.get("lot_size") or ipo.get("lot_size")
    if lot:
        content += f"📦 每手: **{lot}** 股\n"

    fee = ipo.get("entry_fee") or raw.get("entry_fee")
    if fee:
        content += f"🎫 入场费: **{fee:,.0f}** HKD\n"

    if deadline:
        content += f"⏰ 招股截止: **{deadline}**\n"

    grey = ipo.get("grey_market_date") or raw.get("grey_market_date")
    if grey:
        content += f"🌙 暗盘: **{grey}**\n"

    list_date = raw.get("listing_date") or ipo.get("listing_date", "")
    if list_date:
        content += f"🗓️ 上市日: **{list_date}**\n"

    industry = ipo.get("industry") or raw.get("industry", "")
    if industry:
        content += f"🏭 行业: {industry}\n"

    # 杠杆提示
    if is_open and fee:
        content += f"\n💡 **10倍杠杆参考:** 需约 **{fee * 10:,.0f}** HKD 融资额度\n"

    # 维度评分
    content += "\n**维度评分:**\n"
    dims = score["dimensions"]
    for k in sorted(dims, key=dims.get, reverse=True)[:5]:
        from analyzer.scorer import _dim_label
        bar = "█" * int(dims[k] / 10) + "░" * (10 - int(dims[k] / 10))
        content += f"  {_dim_label(k)}: {bar} {dims[k]:.0f}\n"

    # 详情按钮
    detail_url = f"http://www.aastocks.com/sc/stocks/market/ipo/upcomingipo/company-summary?symbol={code}"

    send_card(
        title=f"🆕 港股新股速报 — {code} {name}",
        content=content,
        color="blue" if is_open else "gray",
        button_text="📋 查看招股书" if is_open else "",
        button_url=detail_url if is_open else "",
    )


def push_subscription_update(ipo: dict, old_mult: float, new_mult: float):
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

    send_card(
        title=f"📊 认购热度更新 — {code}",
        content=content,
        color="orange",
    )


def push_score_report(ipo: dict, score: dict):
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

    send_card(
        title=f"🎯 打新建议 — {code} ({rec})",
        content=content,
        color="green" if total >= 65 else "red",
    )


def push_dark_pool(ipo: dict, dark_data: dict, score: dict):
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

    send_card(
        title=f"🌙 暗盘播报 — {code}",
        content=content,
        color="green" if pct >= 0 else "red",
    )


def push_error(msg: str):
    """错误通知"""
    send_card(
        title="⚠️ 港股打新监控异常",
        content=msg,
        color="red",
    )


def push_hot_ipo(ipo: dict, mult: float):
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

    send_card(
        title=f"🔥 热门新股 — {code} {name} ({mult:,.0f}倍)",
        content=content,
        color="red",
    )
