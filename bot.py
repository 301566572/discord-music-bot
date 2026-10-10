"""
Discord 音乐机器人 - 主入口
"""
import os
import random
import signal
import asyncio
from pathlib import Path
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()

HELP_FILE = Path(__file__).resolve().parent / "docs" / "index.html"
DEFAULT_HELP_URL = "https://301566572.github.io/discord-music-bot/"
HELP_URL = (os.getenv("HELP_URL") or DEFAULT_HELP_URL).strip()

# ─── Bot 配置 ───
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(
    command_prefix=["！", "!"],  # 同时支持中文！和英文!
    intents=intents,
    description="🎵 Discord 音乐机器人",
    help_command=None,
)


def _public_help_url() -> str | None:
    """Return only a public HTTP(S) URL suitable for a Discord link button."""
    if HELP_URL.startswith(("https://", "http://")):
        return HELP_URL
    return None


class HelpCenterView(discord.ui.View):
    def __init__(self, url: str):
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Button(
                label="打开完整帮助中心",
                style=discord.ButtonStyle.link,
                url=url,
            )
        )


def build_basic_help_embed() -> discord.Embed:
    """Build the intentionally small in-Discord help surface."""
    embed = discord.Embed(
        title="🎵 小小电台",
        description=(
            "先加入语音频道，再在文字频道发送命令。"
            "支持 `！`、`!` 和 `/` 三种输入方式。"
        ),
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name="基础播放",
        value=(
            "`！播放 <歌名/链接>` 点歌\n"
            "`！b站 <歌名/链接>` 使用 B站音源\n"
            "`！暂停` / `！继续` 控制播放\n"
            "`！下一首` 跳过当前歌曲\n"
            "`！队列` 查看当前播放顺序"
        ),
        inline=False,
    )
    embed.add_field(
        name="歌单与歌词",
        value=(
            "`！创建歌单 [名称]` 新建本地歌单\n"
            "`！歌单 [名称]` 查看歌单\n"
            "`！播放歌单 <名称>` 播放歌单并显示歌词\n"
            "`！歌词 [歌名]` 查看歌词"
        ),
        inline=False,
    )
    embed.add_field(
        name="互动与退出",
        value=(
            "`！猜歌 [轮数] [难度]` 开始猜歌\n"
            "`！停止` 清空状态并离开语音\n"
            "`！帮助网页` 查看完整图文教程和全部命令"
        ),
        inline=False,
    )
    embed.set_footer(text="示例：！播放 稻香  |  ！猜歌 5 0")
    return embed


@bot.hybrid_command(
    name="帮助",
    aliases=["help"],
    description="查看常用基础命令",
    help="查看常用基础命令",
)
async def help_command(ctx: commands.Context):
    url = _public_help_url()
    view = HelpCenterView(url) if url else None
    await ctx.send(embed=build_basic_help_embed(), view=view, silent=True)


@bot.hybrid_command(
    name="帮助网页",
    aliases=["webhelp", "网页帮助", "帮助中心"],
    description="下载可搜索和翻页的完整帮助中心",
    help="下载可搜索和翻页的完整 HTML 帮助中心",
)
async def web_help_command(ctx: commands.Context):
    url = _public_help_url()
    if url:
        embed = discord.Embed(
            title="📖 小小电台完整帮助中心",
            description="包含全部命令、图示工作流、歌单教程和故障排查。",
            color=discord.Color.blurple(),
        )
        return await ctx.send(
            embed=embed,
            view=HelpCenterView(url),
            silent=True,
        )
    if not HELP_FILE.exists():
        return await ctx.send("帮助中心文件不存在，请联系机器人管理员。", silent=True)
    await ctx.send(
        "完整帮助中心已附上。下载后用浏览器打开即可搜索、翻页和复制命令。",
        file=discord.File(HELP_FILE, filename="小小电台-帮助中心.html"),
        silent=True,
    )

# ─── 状态轮播列表 ───
ONLINE_STATUSES = [
    (discord.ActivityType.listening, "你的点歌 | /播放"),
    (discord.ActivityType.playing, "音乐DJ上线啦~"),
    (discord.ActivityType.watching, "等你来点歌 🎤"),
    (discord.ActivityType.listening, "全宇宙最好听的歌"),
    (discord.ActivityType.playing, "蹦迪模式已激活 🪩"),
    (discord.ActivityType.watching, "谁来点首歌？"),
    (discord.ActivityType.listening, "隔壁老王的歌单"),
    (discord.ActivityType.playing, "24小时营业的KTV 🎵"),
    (discord.ActivityType.competing, "谁是点歌王"),
    (discord.ActivityType.listening, "来自B站的好歌"),
]

PLAYING_STATUSES = [
    (discord.ActivityType.listening, "🎶 嗨起来！"),
    (discord.ActivityType.playing, "🎵 放歌中，别打扰"),
    (discord.ActivityType.listening, "🔊 音乐轰炸中"),
    (discord.ActivityType.playing, "🎧 沉浸式听歌"),
]


@tasks.loop(minutes=5)
async def rotate_status():
    """每 5 分钟随机切换一个状态"""
    if bot.voice_clients:
        activity_type, name = random.choice(PLAYING_STATUSES)
    else:
        activity_type, name = random.choice(ONLINE_STATUSES)
    await bot.change_presence(
        status=discord.Status.online,
        activity=discord.Activity(type=activity_type, name=name),
    )


# ─── 静音发送：所有命令回复默认不触发推送通知 ───
@bot.before_invoke
async def _make_ctx_silent(ctx):
    """猴补丁: 让 ctx.send 默认 silent=True，消息正常可见但不弹通知"""
    _original_send = ctx.send

    async def _silent_send(content=None, **kwargs):
        kwargs.setdefault("silent", True)
        return await _original_send(content, **kwargs)

    ctx.send = _silent_send


@bot.event
async def on_ready():
    print(f"✅ 机器人已上线: {bot.user} (ID: {bot.user.id})")
    print(f"📡 已连接 {len(bot.guilds)} 个服务器")
    await bot.change_presence(
        status=discord.Status.online,
        activity=discord.Activity(
            type=discord.ActivityType.playing, name="刚睡醒，准备开工 🎵"
        ),
    )
    if not rotate_status.is_running():
        rotate_status.start()
    try:
        synced = await bot.tree.sync()
        print(f"🔄 已同步 {len(synced)} 个斜杠命令")
    except Exception as e:
        print(f"⚠️ 同步斜杠命令失败: {e}")


@bot.event
async def on_voice_state_update(member, before, after):
    """机器人加入/离开语音频道时刷新状态"""
    if member.id != bot.user.id:
        return
    await asyncio.sleep(1)
    if bot.voice_clients:
        activity_type, name = random.choice(PLAYING_STATUSES)
    else:
        activity_type, name = random.choice(ONLINE_STATUSES)
    await bot.change_presence(
        status=discord.Status.online,
        activity=discord.Activity(type=activity_type, name=name),
    )


@bot.event
async def on_message(message):
    if message.author.bot:
        return
    await bot.process_commands(message)


@bot.event
async def on_command_error(ctx, error):
    # 错误消息也静音
    if isinstance(error, commands.CommandNotFound):
        await ctx.send(
            "❌ 未知命令，输入 `！帮助` 或 `/帮助` 查看所有可用命令。",
            silent=True,
        )
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ 缺少参数: `{error.param.name}`", silent=True)
    else:
        await ctx.send(f"❌ 发生错误: {error}", silent=True)
        raise error


async def graceful_shutdown():
    """优雅关闭：改状态 → 断开语音 → 关闭"""
    print("📢 正在下线...")
    try:
        await bot.change_presence(
            status=discord.Status.idle,
            activity=discord.Activity(
                type=discord.ActivityType.playing, name="下班了，明天见 👋"
            ),
        )
        await asyncio.sleep(2)
    except Exception:
        pass
    for vc in bot.voice_clients:
        try:
            await vc.disconnect()
        except Exception:
            pass
    try:
        await bot.change_presence(status=discord.Status.invisible)
        await asyncio.sleep(1)
    except Exception:
        pass
    await bot.close()


async def main():
    async with bot:
        await bot.load_extension("cogs.music")
        print("🎵 音乐模块已加载")
        await bot.load_extension("cogs.game")
        print("🎮 猜歌游戏模块已加载")
        await bot.load_extension("cogs.diagnostics")
        print("🛠️ 诊断模块已加载")
        token = os.getenv("DISCORD_TOKEN")
        if not token:
            print("❌ 错误: 请在 .env 文件中设置 DISCORD_TOKEN")
            return
        loop = asyncio.get_event_loop()

        def signal_handler():
            asyncio.ensure_future(graceful_shutdown())

        try:
            loop.add_signal_handler(signal.SIGINT, signal_handler)
            loop.add_signal_handler(signal.SIGTERM, signal_handler)
        except NotImplementedError:
            pass
        await bot.start(token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 机器人已关闭")
