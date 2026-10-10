# 🎵 Discord 音乐机器人

一个功能完整的 Discord 音乐机器人，支持 YouTube / Bilibili (B站) / 网易云音乐 搜索播放、歌单导入、播放队列、音量控制、循环播放等功能。

---

## 功能列表

| 命令 | 别名 | 说明 |
|------|------|------|
| `！播放 <关键词/URL>` | `！play`, `！放歌`, `！来一首`, `！点歌`, `！听` | 搜索播放；YouTube 未命中时自动尝试 B站 |
| `！b站 <关键词/URL>` | `！bplay`, `！哔哩哔哩`, `！b站播放` | 从B站搜索并播放音乐 |
| `！网易云 <歌单链接/ID>` | `！netease`, `！网易云歌单`, `！歌单播放` | 播放网易云音乐歌单 |
| `！收藏 <B站收藏夹链接>` | `！b站收藏`, `！收藏夹`, `！fav` | 播放B站收藏夹 |
| `！合集 <B站合集链接>` | `！b站合集`, `！系列`, `！up合集` | 播放B站UP主合集/系列 |
| `！绑定b站` | `！上传cookies`, `！绑定bili` | 绑定你的B站账号（上传cookies） |
| `！解绑b站` | `！删除cookies`, `！解绑bili` | 解绑你的B站账号 |
| `！暂停` | `！pause`, `！等一下`, `！停一下` | 暂停当前播放 |
| `！继续` | `！resume`, `！接着放`, `！继续播放` | 恢复播放 |
| `！下一首` | `！skip`, `！切歌`, `！换一首`, `！跳过` | 跳过当前曲目 |
| `！投票跳过` | `！voteskip`, `！vskip`, `！投票切歌` | 多人投票跳过当前曲目 |
| `！停止` | `！stop`, `！退出`, `！走吧`, `！拜拜` | 停止播放并离开频道 |
| `！队列` | `！queue`, `！列表`, `！播放列表` | 查看当前临时播放队列 |
| `！创建歌单 [名称]` | `！createplaylist`, `！新建歌单` | 启动对话，逐首创建本地歌单 |
| `！歌单添加 <名称> [歌曲/链接]` | `！playlistadd`, `！添加到歌单` | 添加指定歌曲；不填歌曲时添加当前歌曲 |
| `！歌单 [名称]` | `！查看歌单`, `！歌单详情`, `！队列库` | 不填名称列出歌单，填名称查看内容并翻页 |
| `！导出队列 [名称]` | `！exportqueue`, `！队列导出` | 不填名称时发送 JSON 附件，填名称时保存到本地队列库 |
| `！保存歌单 <名称>` | `！savequeue`, `！保存队列` | 把当前队列永久保存为本地歌单 |
| `！播放歌单 <名称>` | `！playqueue`, `！播放队列` | 读取本地歌单并加入播放队列 |
| `！自动歌词 [开/关]` | `！autolyrics`, `！歌词开关` | 控制换歌时是否自动显示歌词 |
| `！歌词 [关键词]` | `！lyrics`, `！lrc`, `！词` | 显示歌词；QQ音乐未命中时自动尝试 LRCLIB |
| `！上传队列 <名称>` | `！uploadqueue`, `！上传歌单` | 上传 JSON 附件并保存到本地队列库 |
| `！删除歌单 <名称>` | `！deletequeue`, `！删除队列` | 删除本地命名歌单 |
| `！导入队列 [名称]` | `！importqueue`, `！队列导入`, `！恢复队列` | 从 JSON 附件导入队列；填名称时保存到本地队列库 |
| `！在听什么` | `！np`, `！当前`, `！这首是什么` | 查看正在播放的曲目 |
| `！音量 <0-100>` | `！volume`, `！声音` | 设置音量 |
| `！单曲循环` | `！loop`, `！循环`, `！重复` | 切换单曲循环 |
| `！列表循环` | `！loopqueue`, `！全部循环` | 切换列表循环 |
| `！滤镜列表` | `！filters`, `！音效列表`, `！效果列表` | 查看可用音效滤镜 |
| `！随机` | `！shuffle`, `！打乱`, `！随机播放` | 随机打乱队列 |
| `！移除 <位置>` | `！remove`, `！删掉`, `！删除` | 移除队列中指定曲目 |
| `！跳转 <位置>` | `！skipto`, `！跳到` | 跳转到队列指定位置 |
| `！清空` | `！clear`, `！全部删除`, `！清除` | 清空播放队列 |
| `！诊断` | `！diagnose`, `！health`, `！状态检查` | 检查 Token、FFmpeg、语音依赖和已加载模块 |
| `！猜歌 [轮数] [难度]` | `！guess`, `！猜歌游戏` | 开始猜歌；优先使用 B站音源，难度为 0-3 |
| `！猜歌分数` | `！gamescore`, `！猜歌排行` | 查看当前猜歌积分 |
| `！结束猜歌` | `！stopgame`, `！游戏结束` | 提前结束并恢复猜歌前的播放队列 |
| `！帮助网页` | `！webhelp`, `！帮助中心` | 打开带图示、工作流、搜索和翻页的在线帮助中心 |

> 中文 `！` 和英文 `!` 都可以用，两种感叹号都识别。

`！帮助` 只显示最常用的基础操作，让 Discord 内的帮助界面保持简洁；高级播放控制、导入导出、滤镜、Cookie 和维护命令统一放在 `！帮助网页` 中。

帮助中心通过 GitHub Pages 公开访问：

[打开小小电台帮助中心](https://301566572.github.io/discord-music-bot/)

需要部署到其他地址时，可在 `.env` 覆盖：

```env
HELP_URL=https://你的帮助页面地址/
```

`！帮助` 和 `！帮助网页` 都会显示可直接打开的链接按钮；本地自包含页面位于 `docs/index.html`。

创建并播放带自动歌词的歌单:

```text
！创建歌单
# 根据提示输入歌单名称，然后每次发送一首歌名或链接
完成歌单
！播放歌单 通勤
```

创建期间输入 `完成歌单` 会保存，输入 `取消创建` 会放弃本次创建。
`！播放歌单` 会自动开启歌词；可用 `！自动歌词 关` 随时关闭。

`队列` 是当前临时播放顺序；`歌单` 是保存在 `data/queues/<服务器ID>/` 下的长期内容。使用 `！保存歌单 <名称>` 可把当前队列转为歌单，使用 `！播放歌单 <名称>` 会把歌单内容加入播放队列。

猜歌示例:

```text
！猜歌 5 0
```

第一个数字是轮数，第二个数字是难度：`0` 混合、`1` 简单、`2` 中等、`3` 困难。简单、中等、困难会分别播放约 45、40、35 秒；长歌曲从总时长约 30% 的位置开始，避开片头和过长前奏，短歌曲则自动从头播放。猜歌优先使用发起者绑定的 B站 cookies；B站音频流无法启动时会自动尝试备用来源。游戏开始前正在播放的歌曲和等待队列会暂存，游戏结束后自动恢复。

---

## 快速开始

### 1. 创建 Discord Bot

1. 打开 [Discord Developer Portal](https://discord.com/developers/applications)
2. 点击 **New Application**，输入名称，创建应用
3. 进入 **Bot** 页面，点击 **Reset Token**，复制 Token（妥善保存！）
4. 在 Bot 页面开启以下权限:
   - ✅ **MESSAGE CONTENT INTENT**
   - ✅ **SERVER MEMBERS INTENT**（可选）
5. 进入 **OAuth2 → URL Generator**:
   - Scopes: 勾选 `bot`, `applications.commands`
   - Bot Permissions: 勾选 `Send Messages`, `Connect`, `Speak`, `Embed Links`, `Read Message History`
6. 复制生成的链接，在浏览器中打开，将机器人邀请到你的服务器

### 2. 安装依赖

**前置要求:**
- Python 3.10+
- FFmpeg（音频处理必须）

```bash
# 安装 FFmpeg
# macOS
brew install ffmpeg

# Ubuntu / Debian
sudo apt update && sudo apt install ffmpeg -y

# Windows: 下载 https://ffmpeg.org/download.html 并添加到 PATH
```

```bash
# 安装 Python 依赖
pip install -r requirements.txt
```

### 3. 配置 Token

```bash
# 复制示例配置
cp .env.example .env

# 编辑 .env 文件，填入你的 Bot Token
DISCORD_TOKEN=你的真实Token
```

### 4. 启动机器人

```bash
python bot.py
```

看到以下输出说明启动成功:
```
🎵 音乐模块已加载
✅ 机器人已上线: YourBot#1234 (ID: 123456789)
📡 已连接 1 个服务器
🔄 已同步 0 个斜杠命令
```

### 5. 图形启动器

项目提供了一个简易 UI 启动器:

```text
start_bot_ui.vbs
```

双击桌面上的 `Discord Music Bot` 快捷方式即可打开图形界面。界面里可以启动/停止机器人，并查看运行日志；启动 bot 时不会额外弹出终端窗口。

如果快捷方式提示找不到 Python，请先创建 `.venv` 并安装依赖，或把 Python 加入 PATH。

---

## 使用示例

```
！播放 周杰伦 稻香          # YouTube 未命中时自动尝试 B站
！播放 https://youtube.com/watch?v=xxx  # 直接播放YouTube链接
！播放 https://www.bilibili.com/video/BVxxx  # 直接播放B站链接
！b站 稻香                  # 从B站搜索并播放
！哔哩哔哩 周杰伦            # 中文命令搜索B站
！网易云 123456             # 播放网易云歌单（歌单ID）
！网易云 https://music.163.com/playlist?id=123456  # 歌单链接也行
！收藏 https://space.bilibili.com/.../favlist  # 播放B站收藏夹
！合集 https://space.bilibili.com/xxx/channel/collectiondetail?sid=xxx  # 播放UP主合集
！队列                      # 查看队列
！音量 80                   # 音量调到 80%
！单曲循环                   # 开启单曲循环
！下一首                    # 跳过这首
！停止                      # 停止并退出
！在听什么                   # 看看现在放的什么
```

---

## 项目结构

```
discord-music-bot/
├── bot.py              # 主入口，Bot 配置和启动
├── harness.py          # 离线逻辑验证 harness
├── HARNESS.md          # harness 说明和扩展规则
├── IMPROVEMENT_PLAN.md # 后续改进计划
├── CHANGELOG.md        # 按日期记录功能与修复
├── docs/
│   └── index.html      # GitHub Pages 图文帮助中心
├── data/
│   └── queues/         # 本地命名队列库，按服务器ID分目录保存
├── cogs/
│   ├── __init__.py
│   ├── diagnostics.py  # 运行环境诊断命令
│   ├── game.py         # 猜歌游戏命令
│   ├── game_logic.py   # 猜歌匹配等纯逻辑
│   ├── lyrics_utils.py # 歌词搜索候选词提取
│   ├── music.py        # 音乐功能命令
│   ├── playlist_parsers.py # 歌单/链接解析工具
│   └── services/       # HTTP、音源、歌词、网易云、cookies 等共享服务
├── requirements.txt    # Python 依赖
├── .env.example        # 环境变量模板
└── README.md           # 本文件
```

## 离线验证

不需要 Discord Token 或网络即可验证核心解析逻辑:

```bash
python harness.py
```

该 harness 现有 31 项检查，覆盖 B站/网易云链接解析、多音源搜索回退、歌词候选词与 LRCLIB 归一化、猜歌答案匹配、cookie 解析、诊断格式化、HTTP helper 注入、队列快照校验和命名队列存储等逻辑。
更多说明见 `HARNESS.md`。

---

## 常见问题

**Q: 播放没声音？**
→ 确认已安装 FFmpeg 并可在终端运行 `ffmpeg -version`

**Q: 搜索失败？**
→ 尝试更新 yt-dlp: `pip install -U yt-dlp`

**Q: 机器人加入了频道但不播放？**
→ 检查机器人是否有语音频道的 `Connect` 和 `Speak` 权限

**Q: 如何让机器人 24/7 在线？**
→ 部署到云服务器（如 AWS, 阿里云, 腾讯云）或使用 Docker 容器运行

---

## Cookies 设置（可选，用于B站收藏夹）

**每个用户可以绑定自己的B站账号**，互不影响。

1. 安装浏览器扩展 [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
2. 在 B站登录状态下，点击扩展图标导出 `cookies.txt`
3. 在 Discord 里发送 `!绑定b站` 并附带 `cookies.txt` 文件（建议私聊机器人发送更安全）
4. 绑定成功后就可以用 `!收藏 <链接>` 播放自己的收藏夹

解绑：`!解绑b站`

Cookies 文件保存在 `cookies/` 目录下，以用户ID命名，每个人独立。

---

## 技术栈

- **discord.py** — Discord API 封装
- **yt-dlp** — YouTube / Bilibili 音频提取
- **requests** — 网易云 API 请求
- **FFmpeg** — 音频流处理
- **PyNaCl** — 语音加密支持
