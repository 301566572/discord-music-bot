# 后续改进计划

## 近期

- [进行中] 把 `cogs/music.py` 继续拆成服务层模块，让命令层只负责 Discord 交互。
- [已完成] 抽出 `services/media_search.py`，复用 yt-dlp 单结果提取逻辑。
- [已完成] 抽出 `services/netease.py`，承载网易云歌单获取和歌曲结构归一化。
- [已完成] 抽出共享 `services` 包，并复用 B站 cookies.txt 解析逻辑。
- [已完成] 增加 `！诊断` 命令，检查 Token、FFmpeg、Python、PyNaCl 和已加载模块。
- [进行中] 给 B站、网易云和 QQ 音乐请求加统一的超时、重试、错误分类与日志上下文。
- [已完成] 增加 `services/http.py`，网易云、B站 API、QQ 音乐歌词请求已接入统一超时/重试 helper。
- 为播放队列增加轻量持久化，机器人重启后可以恢复每个服务器的队列和音量设置。
- [已完成] 增加投票跳过：`！投票跳过`。
- [已完成] 增加队列导出/导入：`！导出队列`、`！导入队列`。
- [已完成] 增加本地命名队列库：`data/queues/<服务器ID>/<名称>.json`，支持保存、上传、列出、读取播放、删除。

## 中期

- 用 dependency injection 注入搜索器和 HTTP client，方便做离线测试和模拟失败场景。
- 把猜歌歌曲库移到 JSON/YAML，支持服务器自定义曲库和难度。
- 增加权限策略，例如限制谁可以清空队列、停止播放或上传 cookies。

## 长期

- 增加结构化日志和运行指标，追踪搜索耗时、播放失败原因、断线次数。
- 加 Dockerfile 与部署文档，补齐 `.env.example`、健康检查和 ffmpeg 可用性检查。
- 建立 CI：运行 `python harness.py`、语法检查，以及后续的单元测试套件。
