"""
港股打新监控 - 主入口
GitHub Actions 定时运行，采集数据 → 分析评分 → 推送飞书
"""
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from scraper.hkex import fetch_all, load_state, save_state, get_new_ipos, should_push_subscription, fetch_dark_pool_price
from analyzer.scorer import score_ipo, predict_first_day_return
from notifier.feishu import (
    push_new_ipo, push_subscription_update, push_score_report,
    push_dark_pool, push_error, send_card,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
HISTORY_FILE = DATA_DIR / "history.json"


def load_history() -> dict:
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text())
    return {}


def save_history(history: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2))


def run():
    logger.info("=" * 60)
    logger.info("港股打新监控 - 开始运行")
    logger.info(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 1. 加载状态
    state = load_state()
    history = load_history()

    # 2. 采集数据
    logger.info(">>> 采集数据...")
    try:
        ipos = fetch_all()
    except Exception as e:
        logger.error(f"数据采集失败: {e}")
        push_error(f"数据采集失败: {e}")
        return

    if not ipos:
        logger.info("当前无新股数据")
        save_state(state)
        return

    logger.info(f"共获取 {len(ipos)} 只新股")

    # 3. 处理每只新股
    current_codes = set()
    for ipo in ipos:
        code = ipo.get("code", "")
        if not code:
            continue
        current_codes.add(code)

        # 3a. 检查是否新股
        is_new = code not in state.get("ipos", {})
        old_state = state.get("ipos", {}).get(code, {})

        # 3b. 评分
        score = score_ipo(ipo)
        ipo["predicted_return"] = predict_first_day_return(score, ipo)

        logger.info(f"  {code} {ipo.get('name', '')}: {score['total']}/100 {score['recommendation']}")

        # 3c. 推送判断
        if is_new:
            logger.info(f"  → 新股! 推送通知")
            push_new_ipo(ipo, score)
        else:
            # 认购倍数跳档?
            new_mult = ipo.get("raw", ipo).get("subscription_multiple") or 0
            old_mult = old_state.get("subscription_multiple", 0)
            if new_mult > 0 and should_push_subscription(code, new_mult, state):
                logger.info(f"  → 认购跳档 {old_mult}→{new_mult}, 推送通知")
                push_subscription_update(ipo, old_mult, new_mult)

        # 3d. 暗盘检查 (上市前一日)
        listing_date = ipo.get("raw", ipo).get("listing_date", "")
        if listing_date:
            try:
                ldate = datetime.strptime(str(listing_date)[:10], "%Y-%m-%d")
                today = datetime.now()
                if (ldate - today).days == 1:
                    dark = fetch_dark_pool_price(ipo.get("code", ""))
                    if dark and dark.get("percent") is not None:
                        logger.info(f"  → 暗盘: {dark['percent']:+.1f}%, 推送通知")
                        push_dark_pool(ipo, dark, score)
            except (ValueError, TypeError):
                pass

        # 3e. 更新状态
        state.setdefault("ipos", {})[code] = {
            "name": ipo.get("name", ""),
            "score": score["total"],
            "recommendation": score["recommendation"],
            "subscription_multiple": ipo.get("raw", ipo).get("subscription_multiple", 0),
            "last_seen": datetime.now().isoformat(),
        }

        # 3f. 保存历史
        history[code] = {
            "name": ipo.get("name", ""),
            "score": score,
            "ipo_data": {k: v for k, v in ipo.items() if k != "raw"},
            "updated": datetime.now().isoformat(),
        }

    # 4. 保存状态
    save_state(state)
    save_history(history)

    # 5. 生成汇总
    logger.info("=" * 60)
    logger.info(f"监控完成. 共 {len(current_codes)} 只新股")
    for code in sorted(current_codes):
        s = state["ipos"].get(code, {})
        logger.info(f"  {code} {s.get('name', '')}: {s.get('score', 0)}/100 {s.get('recommendation', '')}")

    logger.info("运行结束")


if __name__ == "__main__":
    run()
