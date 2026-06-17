# 🇭🇰 港股打新监控

全自动港股 IPO 监控、量化评分、策略推演系统。通过 GitHub Actions 定时运行，结果推送到飞书群。

## 功能

- 🆕 **新股检测** — 自动监控港交所新招股公告
- 📊 **11维评分** — 估值/热度/财务/行业/基石/基本面/承销/流动性/绿鞋/股东/法律
- 🎯 **策略推演** — 预测首日涨幅区间，给出申购/观望/回避建议
- 📈 **认购追踪** — 认购倍数跳档实时通知
- 🌙 **暗盘播报** — 上市前暗盘表现跟踪
- 💰 **零成本** — 全部基于 GitHub Actions (免费) + 飞书 Webhook (免费)

## 架构

```
GitHub Actions (定时触发: 09:00/13:00/16:15/17:00 北京时间)
    │
    ├── 数据采集 (港交所披露易 + 雪球)
    ├── 量化评分 (11 维度加权)
    ├── 策略推演 (首日涨幅预测)
    └── 飞书推送 (交互卡片)
```

## 配置

1. Fork 本仓库
2. 在 GitHub Secrets 中添加: `FEISHU_WEBHOOK` = 你的飞书 Webhook 地址
3. 启用 GitHub Actions
4. 完成!

## 本地运行

```bash
pip install -r requirements.txt
export FEISHU_WEBHOOK="https://open.feishu.cn/open-apis/bot/v2/hook/your-token"
python src/main.py
```

## 文件结构

```
├── .github/workflows/ipo-monitor.yml  # GitHub Actions 定时任务
├── src/
│   ├── scraper/hkex.py                # 数据采集 (港交所 + 雪球)
│   ├── analyzer/scorer.py             # 11维度量化评分引擎
│   ├── notifier/feishu.py             # 飞书 Webhook 推送
│   └── main.py                        # 主入口
├── data/
│   ├── state.json                     # 运行状态 (去重)
│   └── history.json                   # 历史评分数据
└── config.yaml                        # 配置文件
```

## 免责声明

本工具仅供研究参考，不构成投资建议。投资有风险，入市需谨慎。
