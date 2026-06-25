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

from scraper.hkex import fetch_all, load_state, save_state
from analyzer.scorer import score_ipo, predict_first_day_return
from analyzer.ai_analyzer import ai_analyze
from notifier.feishu import push_error, push_new_ipo

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
    logger.info(f"已知新股: {len(state.get('ipos', {}))} 只, 已推送: {sum(1 for v in state.get('ipos', {}).values() if v.get('pushed'))}")

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
        pushed_before = old_state.get("pushed", False)
        hot_pushed = old_state.get("hot_pushed", False)

        if is_new or not pushed_before:
            # 第一次出现 → 推送新股通知
            logger.info(f"  → 新股! AI 分析 + 推送通知")
            analysis = ai_analyze(ipo, score)
            pushed_before = push_new_ipo(ipo, score, ai_analysis=analysis)
            if not pushed_before:
                logger.warning(f"  {code} 新股通知发送失败, 下次继续重试")
        else:
            # 已推送过, 检查是否需要"热门追加推送"
            new_mult = ipo.get("raw", ipo).get("subscription_multiple") or 0
            if new_mult >= 500 and not hot_pushed:
                logger.info(f"  → 认购 {new_mult} 倍! 热门追加推送")
                from notifier.feishu import push_hot_ipo
                hot_pushed = push_hot_ipo(ipo, new_mult)
                if not hot_pushed:
                    logger.warning(f"  {code} 热门通知发送失败, 下次继续重试")
            else:
                logger.info(f"  {code} 已推送过, 跳过")

        # 3d. 更新状态
        # 判断招股状态
        apply_dl = ipo.get("apply_deadline", "")
        status = "open"
        if apply_dl:
            try:
                dl = datetime.strptime(apply_dl.replace("/", "-"), "%Y-%m-%d")
                if dl.date() < datetime.now().date():
                    status = "expired"
            except (ValueError, TypeError):
                pass

        state.setdefault("ipos", {})[code] = {
            "name": ipo.get("name", ""),
            "score": score["total"],
            "recommendation": score["recommendation"],
            "subscription_multiple": ipo.get("raw", ipo).get("subscription_multiple", 0),
            "status": status,
            "apply_deadline": apply_dl,
            "listing_date": ipo.get("listing_date", ""),
            "pushed": pushed_before,
            "hot_pushed": hot_pushed,
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
