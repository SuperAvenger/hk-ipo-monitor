import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from notifier.feishu import push_hot_ipo, push_new_ipo
import main


class NotificationResultTests(unittest.TestCase):
    def test_new_ipo_returns_delivery_result(self):
        ipo = {"code": "01234", "name": "测试股份"}
        score = {
            "total": 60,
            "recommendation": "建议申购",
            "phase": 1,
            "dimensions": {},
        }

        with patch("notifier.feishu.send_card", return_value=True):
            self.assertTrue(push_new_ipo(ipo, score))
        with patch("notifier.feishu.send_card", return_value=False):
            self.assertFalse(push_new_ipo(ipo, score))

    def test_hot_ipo_returns_delivery_result(self):
        ipo = {"code": "01234", "name": "测试股份"}

        with patch("notifier.feishu.send_card", return_value=True):
            self.assertTrue(push_hot_ipo(ipo, 500))
        with patch("notifier.feishu.send_card", return_value=False):
            self.assertFalse(push_hot_ipo(ipo, 500))

    def test_unsent_existing_ipo_is_retried(self):
        state = {
            "ipos": {
                "01234": {
                    "name": "测试股份",
                    "pushed": False,
                    "hot_pushed": False,
                }
            }
        }
        ipo = {"code": "01234", "name": "测试股份"}
        score = {"total": 60, "recommendation": "建议申购", "phase": 1}

        with (
            patch.object(main, "load_state", return_value=state),
            patch.object(main, "load_history", return_value={}),
            patch.object(main, "fetch_all", return_value=[ipo]),
            patch.object(main, "score_ipo", return_value=score),
            patch.object(main, "predict_first_day_return", return_value="0%~5%"),
            patch.object(main, "ai_analyze", return_value={}),
            patch.object(main, "push_new_ipo", return_value=True) as push_new,
            patch.object(main, "save_state"),
            patch.object(main, "save_history"),
        ):
            main.run()

        push_new.assert_called_once()
        self.assertTrue(state["ipos"]["01234"]["pushed"])


if __name__ == "__main__":
    unittest.main()
