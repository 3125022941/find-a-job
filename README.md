# find-a-job · 秋招提前批监控

每天监控小红书上「互联网大厂秋招提前批 / 校招提前批」的动静，自动打分、去重、生成进展总表。

## 目录结构

```
find-a-job/
├── Spider_XHS/                  # 小红书采集引擎（第三方，已 vendored）+ 招聘监控封装
│   ├── xhs_recruit_collect.py   # ⭐ 招聘监控主脚本（采集→打分→去重→落文件）
│   ├── recruit_config.yaml      # 关键词 / 公司 / 加分词 / 搜索参数
│   ├── README_招聘监控.md        # 详细使用说明
│   ├── recruit_out/             # 产出：进展总表 / 每日快照 / 去重库
│   └── .env.example             # cookie 配置模板（复制为 .env 填入）
└── recruit_monitor/             # 早期版本：基于 Bing 收录页的轻量监控（无需 cookie）
```

## 快速开始

```bash
cd Spider_XHS
pip install -r requirements.txt
npm install                      # 签名算法需要 Node 20+

cp .env.example .env             # 然后填入你的小红书 cookie
python xhs_recruit_collect.py --dry-run   # 试跑
python xhs_recruit_collect.py             # 正式跑：写去重 + 更新总表
```

产出在 `Spider_XHS/recruit_out/`：
- `2027提前批进展.md` —— 各大厂最新信号总表
- `logs/check-YYYY-MM-DD.md` —— 每日快照

详细说明见 [Spider_XHS/README_招聘监控.md](Spider_XHS/README_招聘监控.md)。

## 安全 & 合规

- **cookie 存在 `.env`，已被 `.gitignore` 排除，切勿提交。**
- Spider_XHS 逆向了小红书风控签名，平台更新可能失效；用自己 cookie 高频抓取有封号风险。
- 仅用于个人监控公开招聘信息，数据以各公司官方校招页为准。

## 致谢

采集引擎来自 [cv-cat/Spider_XHS](https://github.com/cv-cat/Spider_XHS)（MIT），本仓库在其上增加了招聘监控封装。
