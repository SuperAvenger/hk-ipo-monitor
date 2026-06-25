"""
AI 分析模块 - LLM 深度分析 + 规则引擎降级
"""
import json
import logging
import os
import re
from typing import Optional

import requests

logger = logging.getLogger(__name__)


# ── 规则引擎 (无需 LLM) ─────────────────────────────────────

def _rule_based_analysis(ipo: dict, score: dict) -> dict:
    """基于规则的分析, LLM 不可用时的降级方案"""
    name = ipo.get("name", "")
    total = score["total"]
    dims = score.get("dimensions", {})
    raw = ipo.get("raw", ipo)

    # 评级映射
    if total >= 80:
        rating = "强烈推荐"
    elif total >= 65:
        rating = "推荐"
    elif total >= 50:
        rating = "谨慎推荐"
    elif total >= 35:
        rating = "中性"
    else:
        rating = "不推荐"

    # 优势分析
    pros = []
    if dims.get("industry", 0) >= 65:
        pros.append("行业前景好")
    if dims.get("valuation", 0) >= 60:
        pros.append("估值合理")
    if dims.get("cornerstone", 0) >= 60:
        pros.append("有基石投资者背书")
    if dims.get("subscription", 0) >= 60:
        pros.append("认购热度高")
    if dims.get("financial", 0) >= 60:
        pros.append("财务状况良好")

    # 风险分析
    cons = []
    if dims.get("valuation", 0) < 40:
        cons.append("估值偏高")
    if dims.get("financial", 0) < 40:
        cons.append("财务状况较弱")
    if dims.get("subscription", 0) < 30:
        cons.append("认购热度不足")
    if dims.get("fundamentals", 0) < 40:
        cons.append("基本面一般")

    # 策略
    fee = ipo.get("entry_fee", 0)
    if total >= 65 and fee:
        strategy = f"建议申购，入场费{fee:.0f}HKD，可用10倍杠杆"
    elif total >= 50:
        strategy = "可小量参与，控制杠杆倍数"
    else:
        strategy = "建议观望，风险较高"

    # 首日预测
    if total >= 75:
        guess = "+10%~+30%"
    elif total >= 60:
        guess = "+5%~+15%"
    elif total >= 45:
        guess = "-5%~+10%"
    else:
        guess = "-10%~+5%"

    return {
        "rating": rating,
        "confidence": min(8, max(4, int(total / 12))),
        "summary": f"{name}，{rating}，评分{total}/100",
        "pros": pros[:3] if pros else ["行业有一定前景"],
        "cons": cons[:3] if cons else ["新股波动风险"],
        "strategy": strategy,
        "first_day_guess": guess,
        "method": "rule",
    }


# ── LLM 分析 ─────────────────────────────────────────────────

def _get_llm_config() -> dict:
    """获取 LLM 配置"""
    api_key = os.environ.get("LLM_API_KEY", "")
    api_base = os.environ.get("LLM_API_BASE", "")
    model = os.environ.get("LLM_MODEL", "")

    if not api_key:
        try:
            config_path = os.path.expanduser("~/.openclaw/openclaw.json")
            if os.path.exists(config_path):
                with open(config_path) as f:
                    config = json.load(f)
                providers = config.get("models", {}).get("providers", {})
                for prov_name in ["xiaomi-coding", "bailian", "minimax-portal"]:
                    prov = providers.get(prov_name, {})
                    if prov.get("apiKey"):
                        api_key = prov["apiKey"]
                        api_base = prov.get("baseUrl", "")
                        models = prov.get("models", [])
                        if models:
                            model = models[0]["id"]
                        break
        except Exception:
            pass

    if not api_base:
        api_base = "https://api.openai.com/v1"
    if not model:
        model = "gpt-4o-mini"

    return {"api_key": api_key, "api_base": api_base, "model": model}


def analyze_with_llm(ipo: dict, score: dict, search_results: list[dict]) -> Optional[dict]:
    """用 LLM 对新股进行深度分析"""
    config = _get_llm_config()
    if not config["api_key"]:
        logger.warning("No LLM API key, use rule-based analysis")
        return None

    name = ipo.get("name", "")
    code = ipo.get("code", "")
    raw = ipo.get("raw", ipo)
    price = raw.get("price_range") or ipo.get("price_range", "?")
    lot = raw.get("lot_size") or ipo.get("lot_size", "?")
    fee = ipo.get("entry_fee", "?")
    deadline = ipo.get("apply_deadline", "?")
    list_date = raw.get("listing_date") or ipo.get("listing_date", "?")
    industry = ipo.get("industry", "未知")

    search_summary = ""
    for r in search_results[:3]:
        search_summary += f" {r.get('text', '')[:100]}"

    prompt = f"""你是港股打新助手。请按实用、克制、偏交易决策的口吻分析，不要写营销稿。

新股: {code} {name}
行业: {industry}
招股价: {price}
每手: {lot}
入场费: {fee} HKD
截止: {deadline}
上市: {list_date}
量化评分: {score['total']}/100
补充资料: {search_summary}

只输出JSON，不要Markdown，不要代码块。字段如下:
{{"rating":"强烈推荐/推荐/谨慎推荐/中性/不推荐","confidence":7,"summary":"一句话判断，直接说打还是不打","pros":["最多3条利好"],"cons":["最多3条风险"],"strategy":"申购策略，包含是否打、仓位/杠杆倾向、需要复核的关键条件","first_day_guess":"+X%~+Y%"}}"""

    try:
        resp = requests.post(
            f"{config['api_base']}/chat/completions",
            headers={
                "Authorization": f"Bearer {config['api_key']}",
                "Content-Type": "application/json",
            },
            json={
                "model": config["model"],
                "messages": [
                    {"role": "system", "content": "输出JSON。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "max_tokens": 600,
            },
            timeout=60,
        )
        resp.raise_for_status()
        msg = resp.json()["choices"][0]["message"]
        content = msg.get("content", "")

        # reasoning 模型: content 可能为空, 尝试从 reasoning_content 提取
        if not content:
            rc = msg.get("reasoning_content", "")
            if rc:
                m = re.search(r'\{[^{}]*"rating"[^{}]*\}', rc, re.DOTALL)
                if m:
                    content = m.group(0)

        if not content:
            return None

        # 清理 JSON
        content = content.strip()
        m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
        if m:
            content = m.group(1).strip()
        if not content.startswith("{"):
            m = re.search(r"\{.*\}", content, re.DOTALL)
            if m:
                content = m.group(0)

        result = json.loads(content)
        if "rating" not in result:
            return None
        result["method"] = "llm"
        return result

    except Exception as e:
        logger.error(f"LLM analysis failed: {e}")
        return None


# ── 综合分析入口 ─────────────────────────────────────────────

def ai_analyze(ipo: dict, score: dict) -> dict:
    """综合分析: 尝试 LLM, 降级到规则引擎"""
    name = ipo.get("name", "")
    code = ipo.get("code", "")

    # 尝试 LLM 分析
    logger.info(f"  AI 分析: 尝试 LLM...")
    search_results = []
    analysis = analyze_with_llm(ipo, score, search_results)

    if analysis:
        logger.info(f"  AI 评价 (LLM): {analysis.get('rating', '?')} - {analysis.get('summary', '?')}")
        return analysis

    # 降级到规则引擎
    logger.info(f"  AI 分析: LLM 不可用, 使用规则引擎")
    analysis = _rule_based_analysis(ipo, score)
    logger.info(f"  AI 评价 (规则): {analysis.get('rating', '?')} - {analysis.get('summary', '?')}")
    return analysis
