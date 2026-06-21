"""Generate a reviewable WeChat article draft without publishing it."""

from __future__ import annotations

import re
from datetime import datetime
from html import escape
from pathlib import Path

import bleach
from markdown import markdown


RISK_LABELS = {
    "subscription_data_unavailable": "认购数据尚未形成，热度判断可能变化",
    "chapter_18c_company": "属于特专科技公司，商业化与估值不确定性较高",
    "high_entry_fee": "入场费较高，单手资金占用较大",
}

DIMENSION_LABELS = {
    "industry": "行业景气度",
    "subscription": "认购热度",
    "cornerstone": "基石投资者",
    "fundraise": "募资规模",
    "valuation": "估值",
    "entry": "入场成本",
    "fundamentals": "基本面",
    "underwriter": "承销商",
    "liquidity": "流动性",
    "greenshoe": "绿鞋机制",
    "shareholder": "股东背景",
    "legal": "法律与合规",
}


def _value(ipo: dict, key: str, default=""):
    raw = ipo.get("raw") or {}
    return ipo.get(key) or raw.get(key) or default


def _risk_text(flag: str) -> str:
    if flag.startswith("missing_data:"):
        fields = flag.split(":", 1)[1].replace(",", "、")
        return f"部分字段缺失（{fields}），评分置信度受限"
    return RISK_LABELS.get(flag, flag)


def _source_links(ipo: dict) -> list[str]:
    code = str(ipo.get("code", "")).strip()
    links = []
    for label, key in (("港交所披露文件", "hkex_url"), ("招股资料", "source_url")):
        url = _value(ipo, key)
        if url and str(url).startswith(("http://", "https://")):
            links.append(f"- [{label}]({url})")
    if code:
        links.append(
            "- [AASTOCKS 新股资料]"
            f"(http://www.aastocks.com/sc/stocks/market/ipo/upcomingipo/company-summary?symbol={code})"
        )
    return list(dict.fromkeys(links))


def build_wechat_draft(
    ipo: dict,
    score: dict,
    ai_analysis: dict | None = None,
    generated_at: datetime | None = None,
) -> str:
    """Build a factual Markdown draft intended for human review."""
    generated_at = generated_at or datetime.now()
    ai_analysis = ai_analysis or {}
    code = str(ipo.get("code", "")).strip()
    name = str(ipo.get("name", "")).strip()
    total = score.get("total", 0)
    recommendation = score.get("recommendation", "待观察")
    confidence = score.get("confidence") or {}
    confidence_text = {
        "high": "较高",
        "medium": "中等",
        "low": "较低",
    }.get(confidence.get("level"), "未评估")

    title = f"港股打新研究｜{code} {name}：评分 {total}/100，{recommendation}"
    lines = [
        f"# {title}",
        "",
        f"> 备选标题：{name} 值得申购吗？一文看懂关键数据与主要风险",
        "",
        f"> 数据更新时间：{generated_at.strftime('%Y-%m-%d %H:%M')}（北京时间）",
        "",
        "## 核心结论",
        "",
        f"本次模型评分为 **{total}/100**，当前研究结论为 **{recommendation}**。",
    ]

    summary = ai_analysis.get("summary")
    if summary:
        lines.extend(["", str(summary).strip()])

    lines.extend(
        [
            "",
            f"评分置信度：**{confidence_text}**"
            + (f"（字段完整度 {confidence.get('percent')}%）" if confidence.get("percent") is not None else ""),
            "",
            "## 招股关键信息",
            "",
            f"- 股票代码：{code or '待补充'}",
            f"- 公司名称：{name or '待补充'}",
            f"- 行业：{_value(ipo, 'industry', '待补充')}",
            f"- 招股价：{_value(ipo, 'price_range', '待补充')}",
            f"- 每手股数：{_value(ipo, 'lot_size', '待补充')}",
            f"- 入场费：{_value(ipo, 'entry_fee', '待补充')}",
            f"- 招股截止：{_value(ipo, 'apply_deadline', '待补充')}",
            f"- 暗盘日期：{_value(ipo, 'grey_market_date', '待补充')}",
            f"- 上市日期：{_value(ipo, 'listing_date', '待补充')}",
            f"- 认购倍数：{_value(ipo, 'subscription_multiple', '尚无数据')}",
            "",
            "## 评分拆解",
            "",
        ]
    )

    dimensions = score.get("dimensions") or {}
    for key, value in sorted(dimensions.items(), key=lambda item: item[1], reverse=True):
        lines.append(f"- {DIMENSION_LABELS.get(key, key)}：{value:.0f}/100")

    pros = ai_analysis.get("pros") or []
    if pros:
        lines.extend(["", "## 值得关注的因素", ""])
        lines.extend(f"- {item}" for item in pros[:5])

    risks = [_risk_text(flag) for flag in score.get("risk_flags") or []]
    risks.extend(str(item) for item in (ai_analysis.get("cons") or [])[:5])
    lines.extend(["", "## 风险提示", ""])
    if risks:
        lines.extend(f"- {item}" for item in dict.fromkeys(risks))
    else:
        lines.append("- 当前未识别到结构化风险项，仍需阅读招股书并核验最新认购数据。")

    strategy = ai_analysis.get("strategy")
    lines.extend(["", "## 研究计划", ""])
    lines.append(str(strategy).strip() if strategy else "持续跟踪认购热度、配售结果、暗盘表现与上市首日表现。")

    lines.extend(["", "## 资料来源", ""])
    lines.extend(_source_links(ipo) or ["- 待补充并核验原始披露来源"])
    lines.extend(
        [
            "",
            "---",
            "",
            "**免责声明**：本文仅为个人研究记录，不构成任何投资建议或收益承诺。"
            "新股价格波动较大，文中数据可能随招股进程更新，请以港交所及公司正式披露为准。",
            "",
            "<!-- 发布前检查：核验数据、补充原始来源、删除待补充字段、人工确认标题和结论。 -->",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def build_wechat_html(markdown_draft: str, article_title: str) -> str:
    """Render a standalone, copy-friendly HTML preview for manual publishing."""
    rendered = markdown(markdown_draft, extensions=["extra", "sane_lists"])
    body = bleach.clean(
        rendered,
        tags={"h1", "h2", "h3", "p", "ul", "ol", "li", "blockquote", "strong", "em", "a", "hr", "code"},
        attributes={"a": ["href", "title"]},
        protocols={"http", "https"},
        strip=True,
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(article_title)}</title>
  <style>
    body {{ margin: 0; background: #f5f7fa; color: #1f2937; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    article {{ width: min(100% - 32px, 720px); margin: 24px auto; padding: 28px; background: #fff; box-sizing: border-box; }}
    h1 {{ margin: 0 0 22px; font-size: 26px; line-height: 1.4; color: #111827; }}
    h2 {{ margin: 30px 0 12px; padding-left: 10px; border-left: 4px solid #1677ff; font-size: 19px; line-height: 1.5; }}
    p, li {{ font-size: 16px; line-height: 1.85; }}
    blockquote {{ margin: 12px 0; padding: 10px 14px; border-left: 3px solid #94a3b8; background: #f8fafc; color: #475569; }}
    ul {{ padding-left: 24px; }}
    a {{ color: #1677ff; word-break: break-all; }}
    hr {{ margin: 30px 0; border: 0; border-top: 1px solid #e5e7eb; }}
    strong {{ color: #111827; }}
    @media (max-width: 560px) {{ article {{ width: 100%; margin: 0; padding: 20px 16px; }} h1 {{ font-size: 23px; }} }}
  </style>
</head>
<body><article>{body}</article></body>
</html>
"""


def save_wechat_draft(
    ipo: dict,
    score: dict,
    ai_analysis: dict | None = None,
    output_dir: Path | None = None,
    generated_at: datetime | None = None,
) -> Path:
    """Save a draft locally and return its path. No network calls are made."""
    generated_at = generated_at or datetime.now()
    output_dir = output_dir or Path(__file__).parents[2] / "output" / "wechat-drafts"
    output_dir.mkdir(parents=True, exist_ok=True)
    code = re.sub(r"[^0-9A-Za-z_-]+", "-", str(ipo.get("code", "unknown"))).strip("-") or "unknown"
    path = output_dir / f"{generated_at:%Y-%m-%d}-{code}.md"
    draft = build_wechat_draft(ipo, score, ai_analysis=ai_analysis, generated_at=generated_at)
    path.write_text(draft, encoding="utf-8")
    title = f"港股打新研究｜{ipo.get('code', '')} {ipo.get('name', '')}".strip()
    path.with_suffix(".html").write_text(
        build_wechat_html(draft, title),
        encoding="utf-8",
    )
    return path
