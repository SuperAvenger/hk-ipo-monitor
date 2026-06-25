import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

import main
from notifier import feishu


class NotificationStateTests(unittest.TestCase):
    def test_new_ipo_returns_delivery_result(self):
        ipo = {"code": "09999", "name": "测试新股"}
        score = {"total": 80, "recommendation": "推荐", "dimensions": {"quality": 80}}

        with patch("notifier.feishu.send_card", return_value=True):
            self.assertTrue(feishu.push_new_ipo(ipo, score))

        with patch("notifier.feishu.send_card", return_value=False):
            self.assertFalse(feishu.push_new_ipo(ipo, score))

    def test_hot_ipo_returns_delivery_result(self):
        ipo = {"code": "09999", "name": "测试新股"}

        with patch("notifier.feishu.send_card", return_value=True):
            self.assertTrue(feishu.push_hot_ipo(ipo, 600))

        with patch("notifier.feishu.send_card", return_value=False):
            self.assertFalse(feishu.push_hot_ipo(ipo, 600))

    def test_new_ipo_uses_investment_note_sections(self):
        ipo = {
            "code": "06666",
            "name": "样例股份",
            "industry": "消费电子",
            "price_range": "10.00-12.00",
            "lot_size": 200,
            "entry_fee": 2424.2,
            "apply_deadline": "2026-06-30",
            "listing_date": "2026-07-08",
            "subscription_multiple": 88,
        }
        score = {
            "total": 62,
            "recommendation": "🟠 建议申购",
            "dimensions": {"industry": 70, "valuation": 55},
            "phase": 1,
        }

        with patch("notifier.feishu.send_card", return_value=True) as send_card:
            self.assertTrue(feishu.push_new_ipo(ipo, score))

        content = send_card.call_args.kwargs["content"]
        for section in [
            "❶ **公司信息**",
            "❷ **估值 / A-H 折价**",
            "❸ **发行信息**",
            "❹ **基石、绿鞋与保荐人**",
            "❺ **公司财务信息**",
            "❻ **中签率 / 认购热度**",
            "❼ **总结**",
        ]:
            self.assertIn(section, content)
        self.assertIn("招股价：10.00-12.00 HKD", content)
        self.assertIn("认购倍数：88 倍", content)

    @patch("main.save_history")
    @patch("main.save_state")
    @patch("main.ai_analyze", return_value={})
    @patch("main.score_ipo", return_value={"total": 70, "recommendation": "推荐", "dimensions": {}})
    @patch("main.predict_first_day_return", return_value="10%")
    @patch("main.fetch_all")
    @patch("main.load_history", return_value={})
    @patch("main.load_state")
    def test_unsent_existing_ipo_is_retried(
        self,
        load_state,
        load_history,
        fetch_all,
        predict_first_day_return,
        score_ipo,
        ai_analyze,
        save_state,
        save_history,
    ):
        load_state.return_value = {
            "ipos": {
                "09999": {
                    "name": "测试新股",
                    "pushed": False,
                    "hot_pushed": False,
                }
            },
            "hkex_docs": {},
            "last_check": None,
        }
        fetch_all.return_value = [{"code": "09999", "name": "测试新股"}]

        with patch("main.push_new_ipo", return_value=True) as push_new:
            main.run()

        push_new.assert_called_once()
        saved_state = save_state.call_args.args[0]
        self.assertTrue(saved_state["ipos"]["09999"]["pushed"])


if __name__ == "__main__":
    unittest.main()
