"""
港股新股数据采集 - 多源聚合
数据源:
  1. 港交所披露易 titleSearchServlet API — 官方文件 (curl, 有 rate limit)
  2. 雪球 IPO — 行情+认购 (需 cookie, 可能 403)
  3. 新浪港股 IPO — 备用

已知限制:
  - HKEX API 有 TLS 指纹检测 + 请求频率限制, 必须用 curl + 间隔 ≥3s
  - 雪球从 WSL 内网大概率 403
  - 新浪 HK_IPOService 接口已下线 ("Service not valid")
"""
import json
import re
import subprocess
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

DATA_DIR = Path(__file__).parent.parent / "data"
HKEX_SEARCH_URL = "https://www1.hkexnews.hk/search/titleSearchServlet.do"
HKEX_DOC_BASE = "https://www1.hkexnews.hk"

# 港交所 IPO 相关文档关键词 — 实测有效, 能捕获真正的新股
HKEX_IPO_KEYWORDS = [
    "公開發售",      # 正在招股的新股 (最高优先级)
    "聆訊",          # 已通过聆讯的新股
    "招股",          # 招股章程 (含 ETF, 需过滤)
]

# HKEX API 请求间隔 (秒) — 低于此值会触发 rate limit
HKEX_REQUEST_DELAY = 4.0


def _get_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": USER_AGENT,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    })
    return s


# ── 港交所: curl 封装 (绕过 TLS 指纹) ────────────────────────

def _curl_get(url: str, timeout: int = 20) -> Optional[dict]:
    """
    用 curl 发请求 (HKEX API 对 Python requests 返回空结果)。
    返回解析后的 JSON dict, 失败返回 None。
    """
    try:
        result = subprocess.run(
            ["curl", "-s", "-m", str(timeout), url,
             "-H", f"User-Agent: {USER_AGENT}"],
            capture_output=True, text=True, timeout=timeout + 5
        )
        if result.returncode != 0:
            return None
        if not result.stdout.strip():
            return None
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as e:
        logger.warning(f"curl request failed: {e}")
        return None


def fetch_hkex_ipo_docs(days_back: int = 60) -> list[dict]:
    """
    从港交所披露易搜索 IPO 相关文件。
    使用 curl 绕过 TLS 指纹; 每次请求间隔 4s 避免 rate limit。
    """
    today = datetime.now()
    from_date = (today - timedelta(days=days_back)).strftime("%Y%m%d")
    to_date = today.strftime("%Y%m%d")

    all_docs = []
    seen_ids = set()

    for i, keyword in enumerate(HKEX_IPO_KEYWORDS):
        if i > 0:
            time.sleep(HKEX_REQUEST_DELAY)

        try:
            encoded_kw = quote(keyword)
            url = (
                f"{HKEX_SEARCH_URL}?"
                f"sortDir=0&sortByDate=desc&category=0&market=SEHK&stockId=-1"
                f"&documentType=-1&fromDate={from_date}&toDate={to_date}"
                f"&title={encoded_kw}&searchType=0"
                f"&t1code=-2&t2Gcode=-2&t2code=-2&lang=ZH"
            )
            data = _curl_get(url)

            if not data or data.get("result") in (None, "null"):
                logger.info(f"HKEX '{keyword}': 0 results")
                continue

            results = json.loads(data["result"])
            logger.info(f"HKEX '{keyword}': {len(results)} results")

            for r in results:
                news_id = r.get("NEWS_ID", "")
                if news_id in seen_ids:
                    continue
                seen_ids.add(news_id)

                stock_code = _clean_stock_code(r.get("STOCK_CODE", ""))
                if not stock_code:
                    continue  # 无股票代码的跳过

                # 过滤: 跳过结构性产品 (6位代码) 和 ETF
                if _is_structured_or_etf(stock_code, r.get("STOCK_NAME", ""), r.get("TITLE", "")):
                    continue

                # 过滤: 跳过"首次公開發售後"类公告 (购股权/章程修订等, 不是真正的新股)
                if _is_post_ipo_doc(r.get("TITLE", ""), r.get("LONG_TEXT", "")):
                    continue

                doc = {
                    "news_id": news_id,
                    "stock_code": stock_code,
                    "stock_name": r.get("STOCK_NAME", "").strip(),
                    "title": r.get("TITLE", "").strip(),
                    "doc_type": r.get("LONG_TEXT", "").strip(),
                    "date": r.get("DATE_TIME", ""),
                    "file_link": r.get("FILE_LINK", ""),
                    "file_info": r.get("FILE_INFO", ""),
                    "keyword_matched": keyword,
                    "source": "hkex",
                    "doc_url": f"{HKEX_DOC_BASE}{r.get('FILE_LINK', '')}"
                               if r.get("FILE_LINK") else "",
                }
                all_docs.append(doc)

        except Exception as e:
            logger.warning(f"HKEX search for '{keyword}' failed: {e}")
            continue

    logger.info(f"HKEX total: {len(all_docs)} IPO-related documents")
    return all_docs


def _clean_stock_code(raw: str) -> str:
    """清理股票代码, 提取5位数字; 多个代码取第一个"""
    if not raw:
        return ""
    raw = re.sub(r"<br\s*/?>", " ", raw)
    match = re.search(r"(\d{5})", raw)
    if match:
        return match.group(1)
    match = re.search(r"(\d{4})", raw)
    if match:
        return match.group(1).zfill(5)
    return ""


def _is_structured_or_etf(code: str, name: str, title: str) -> bool:
    """
    判断是否为结构性产品 (牛熊证/窝轮) 或 ETF, 这些不是 IPO 新股。
    规则:
      - 6位代码 = 结构性产品
      - 股票名含 ＳＰＤＲ/基金/ETF/信托 = ETF/基金
      - 标题含 牛熊證/認購證/認沽證/structured = 窝轮/牛熊证
    """
    if len(code) > 5:
        return True  # 6位 = 结构性产品

    combined = f"{name} {title}".lower()
    etf_keywords = ["基金", "etf", "spdr", "信托", "trust", "fund"]
    struct_keywords = ["牛熊證", "認購證", "認沽證", "warrants", "cbbc",
                       "structured product", "杠杆"]

    for kw in etf_keywords:
        if kw in combined:
            return True
    for kw in struct_keywords:
        if kw in combined:
            return True
    return False


def _is_post_ipo_doc(title: str, doc_type: str) -> bool:
    """
    判断是否为"首次公開發售後"类公告, 这些是已上市公司的后续文件,
    不是真正的新股招股。包括:
      - 首次公開發售後購股權計劃
      - 首次公開發售後受限制股份單位計劃
      - 首次公開發售後股份激勵計劃
    """
    combined = f"{title} {doc_type}"
    post_ipo_patterns = [
        "首次公開發售後",
        "首次公開招股後",
        "IPO後",
        "post-IPO",
        "post IPO",
    ]
    for pattern in post_ipo_patterns:
        if pattern in combined:
            return True
    return False


# ── 雪球: IPO 列表 ──────────────────────────────────────────

def fetch_xueqiu_ipo_list() -> list[dict]:
    """从雪球获取港股新股列表。大概率 403, 失败返回空列表。"""
    session = _get_session()
    session.headers.update({
        "Origin": "https://xueqiu.com",
        "Referer": "https://xueqiu.com/",
    })
    try:
        session.get("https://xueqiu.com/", timeout=10)
        time.sleep(1)

        url = "https://stock.xueqiu.com/v5/stock/ipo/query.json"
        params = {
            "page": "1", "size": "30",
            "order": "ipo_date", "order_by": "desc",
            "market": "hk",
        }
        resp = session.get(url, params=params, timeout=15)
        if resp.status_code != 200:
            logger.warning(f"Xueqiu returned HTTP {resp.status_code}")
            return []

        data = resp.json()
        ipos = []
        for item in data.get("data", {}).get("list", []):
            symbol = item.get("symbol", "")
            code = re.sub(r"[^0-9]", "", symbol).zfill(5)
            ipos.append({
                "code": code,
                "name": item.get("name", ""),
                "ipo_price": item.get("ipo_price", ""),
                "price_range": f"{item.get('ipo_price_min', '')}-{item.get('ipo_price_max', '')}",
                "listing_date": _ts_to_date(item.get("listing_date")),
                "subscription_start": _ts_to_date(item.get("sub_start_date")),
                "subscription_end": _ts_to_date(item.get("sub_end_date")),
                "subscription_multiple": item.get("over_subscribe_rate", 0),
                "cornerstone": item.get("cornerstone_investor", ""),
                "industry": item.get("industry", ""),
                "lot_size": item.get("lot_size", 0),
                "fundraise": item.get("fund_raising_amount", 0),
                "source": "xueqiu",
                "raw": item,
            })
        logger.info(f"Xueqiu: found {len(ipos)} IPOs")
        return ipos
    except Exception as e:
        logger.warning(f"Xueqiu fetch failed: {e}")
        return []


def fetch_dark_pool_price(symbol: str) -> Optional[dict]:
    """获取暗盘行情"""
    session = _get_session()
    session.headers.update({"Referer": "https://xueqiu.com/"})
    try:
        session.get("https://xueqiu.com/", timeout=10)
        time.sleep(0.5)
        resp = session.get(
            "https://stock.xueqiu.com/v5/stock/quote.json",
            params={"symbol": symbol, "extend": "detail"},
            timeout=15,
        )
        data = resp.json().get("data", {}).get("quote", {})
        if data:
            return {
                "symbol": symbol,
                "current": data.get("current"),
                "percent": data.get("percent"),
                "high": data.get("high"),
                "low": data.get("low"),
                "volume": data.get("volume"),
                "amount": data.get("amount"),
            }
    except Exception as e:
        logger.error(f"Dark pool fetch for {symbol} failed: {e}")
    return None


def _ts_to_date(ts) -> str:
    if not ts:
        return ""
    try:
        ts = int(ts)
        if ts > 1e12:
            ts = ts / 1000
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    except (ValueError, TypeError, OSError):
        return str(ts)


# ── 新浪: 港股 IPO (备用) ──────────────────────────────────

def fetch_sina_hk_ipo() -> list[dict]:
    """新浪港股 IPO 列表 (接口已基本下线, 仅做尝试)"""
    session = _get_session()
    try:
        resp = session.get(
            "https://stock.finance.sina.com.cn/hkstock/api/openapi.php/HK_IPOService.getIPOList",
            params={"type": "all"},
            timeout=15,
        )
        data = resp.json()
        if data.get("result", {}).get("status", {}).get("code") != 0:
            logger.info("Sina HK IPO API: service not available")
            return []
        ipos = []
        for item in data.get("result", {}).get("data", []):
            code = str(item.get("symbol", "")).zfill(5)
            ipos.append({
                "code": code,
                "name": item.get("name", ""),
                "ipo_price": item.get("ipo_price", ""),
                "listing_date": item.get("listing_date", ""),
                "subscription_multiple": item.get("over_subscribe_rate", 0),
                "source": "sina",
                "raw": item,
            })
        logger.info(f"Sina: found {len(ipos)} IPOs")
        return ipos
    except Exception as e:
        logger.warning(f"Sina HK IPO fetch failed: {e}")
        return []


# ── 状态管理 ─────────────────────────────────────────────────

STATE_FILE = DATA_DIR / "state.json"


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"ipos": {}, "hkex_docs": {}, "last_check": None}


def save_state(state: dict):
    state["last_check"] = datetime.now().isoformat()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def get_new_ipos(current_codes: set[str], state: dict) -> set[str]:
    known = set(state.get("ipos", {}).keys())
    return current_codes - known


def should_push_subscription(code: str, new_mult: float, state: dict) -> bool:
    thresholds = [10, 50, 100, 500, 1000, 3000]
    old_mult = state.get("ipos", {}).get(code, {}).get("subscription_multiple", 0)
    for t in thresholds:
        if old_mult < t <= new_mult:
            return True
    return False


# ── 汇总采集 ─────────────────────────────────────────────────

def fetch_all() -> list[dict]:
    """
    汇总所有数据源, 返回合并后的新股列表。
    当前可靠源: HKEX 官方文件 (curl)
    """
    # 1. 港交所官方文件
    hkex_docs = fetch_hkex_ipo_docs(days_back=60)
    hkex_by_code: dict[str, list] = {}
    for doc in hkex_docs:
        code = doc["stock_code"]
        if code:
            hkex_by_code.setdefault(code, []).append(doc)

    # 2. 雪球 (大概率 403)
    xueqiu_ipos = fetch_xueqiu_ipo_list()

    # 3. 新浪 (已下线, 仅尝试)
    sina_ipos = fetch_sina_hk_ipo()

    # 4. 合并
    merged_by_code: dict[str, dict] = {}

    for ipo in xueqiu_ipos:
        code = ipo["code"]
        if code in hkex_by_code:
            ipo["hkex_docs"] = hkex_by_code[code]
        merged_by_code[code] = ipo

    for ipo in sina_ipos:
        code = ipo["code"]
        if code not in merged_by_code:
            if code in hkex_by_code:
                ipo["hkex_docs"] = hkex_by_code[code]
            merged_by_code[code] = ipo

    # 5. HKEX-only (新出现的, 行情源还没收录)
    for code, docs in hkex_by_code.items():
        if code not in merged_by_code:
            merged_by_code[code] = {
                "code": code,
                "name": docs[0].get("stock_name") or docs[0]["title"],
                "source": "hkex_only",
                "hkex_docs": docs,
                "ipo_price": "",
                "price_range": "",
                "listing_date": "",
                "subscription_start": "",
                "subscription_end": "",
                "subscription_multiple": 0,
                "cornerstone": "",
                "industry": "",
                "lot_size": 0,
                "fundraise": 0,
            }

    merged = list(merged_by_code.values())
    logger.info(
        f"Merged: {len(merged)} total IPOs "
        f"(xueqiu={len(xueqiu_ipos)}, sina={len(sina_ipos)}, "
        f"hkex={len(hkex_docs)} docs for {len(hkex_by_code)} stocks)"
    )
    return merged
