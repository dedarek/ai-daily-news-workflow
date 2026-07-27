# 多数据源采集与告警

所有启用源并行运行。单源失败只进入健康报告，不阻断其他源；去重后候选不足 12 条时才阻断日报。

| ID | 独立适配器 | 时间规则 |
|---|---|---|
| `hex2077` | `scripts/news_sources/hex2077.py` | 内容日期等于日报日期 |
| `satori` | `scripts/news_sources/satori.py` | “生成于”的日期等于日报日期，整版视为当天日报 |
| `daheiai` | `scripts/news_sources/daheiai.py` | RSS 最新条目的北京时间日期等于日报日期 |

站点参数位于 `skill/references/news-sources.json`。公共层 `collector.py` 只负责并发、轮询合并、URL 规范化、标题相似去重和健康汇总，不包含任何站点 DOM 或时间规则。

健康报告写入 `dist/source-health-YYYY-MM-DD.json`。任意启用源失败时，GitHub Actions 调用 `send_source_health_alert.py` 给管理员发邮件；只要剩余候选足够，日报仍会继续生成。

## 新增网站

1. 在 `scripts/news_sources/` 新建独立适配器并继承 `SourceAdapter`。
2. 在适配器内实现该站点的抓取、解析、日期校验和最低条数校验。
3. 在 `collector.py` 注册适配器，并在 `news-sources.json` 添加配置。
4. 在 `scripts/tests/test_news_sources.py` 添加离线 HTML/RSS 固定样本测试。

不要把某个网站的 DOM 或发布时间语义写进 `collector.py`。
