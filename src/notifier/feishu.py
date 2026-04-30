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

def push_new_ipo(ipo: dict, score: dict):
    """新股出现通知"""
    code = ipo.get("code", "")
    name = ipo.get("name", "")
    total = score["total"]
    rec = score["recommendation"]
    pred = ipo.get("predicted_return", "")

    # 评分星星
    stars = "⭐" * min(5, int(total / 20))

    content = (
        f"**{code} {name}**\n\n"
        f"📊 综合评分: **{total}/100** {stars}\n"
        f"🎯 建议: **{rec}**\n"
    )

    if pred:
        content += f"📈 预测首日: **{pred}**\n"

    # 关键信息
    raw = ipo.get("raw", ipo)
    if raw.get("price_range"):
        content += f"💰 招股价: {raw['price_range']} HKD\n"
    if raw.get("subscription_start"):
        content += f"📅 认购期: {raw.get('subscription_start', '')} ~ {raw.get('subscription_end', '')}\n"
    if raw.get("listing_date"):
        content += f"🗓️ 上市日: {raw['listing_date']}\n"
    if raw.get("lot_size"):
        content += f"📦 每手: {raw['lot_size']} 股\n"

    # 维度评分
    content += "\n**维度评分:**\n"
    dims = score["dimensions"]
    for k in sorted(dims, key=dims.get, reverse=True)[:5]:
        from analyzer.scorer import _dim_label
        bar = "█" * int(dims[k] / 10) + "░" * (10 - int(dims[k] / 10))
        content += f"  {_dim_label(k)}: {bar} {dims[k]:.0f}\n"

    send_card(
        title=f"🆕 港股新股速报 — {code}",
        content=content,
        color="blue" if total >= 65 else "orange",
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
