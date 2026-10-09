"""
Discord 音乐机器人 - 猜歌游戏模块
支持: 中文歌曲猜歌、多轮游戏、积分排行榜、难度选择
"""
import asyncio
import random
import re
from collections import defaultdict

import discord
from discord.ext import commands
from discord import app_commands

from cogs.game_logic import check_answer as check_guess_answer
from cogs.game_logic import calculate_clip_window
from cogs.game_logic import normalize as normalize_answer_text
from cogs.music import BILI_FFMPEG_OPTIONS, FFMPEG_OPTIONS
from cogs.services.media_search import extract_first

# ─── yt-dlp 配置 (猜歌专用，只提取不下载) ───
GAME_YDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
    "socket_timeout": 20,
}

# ─── 歌曲库 ───
# 每首歌: (歌名, 歌手, 搜索关键词, 难度 1-3)
SONG_DATABASE = [
    # ── 难度 1: 经典华语流行 (几乎人人都知道) ──
    ("稻香", "周杰伦", "周杰伦 稻香", 1),
    ("晴天", "周杰伦", "周杰伦 晴天", 1),
    ("七里香", "周杰伦", "周杰伦 七里香", 1),
    ("青花瓷", "周杰伦", "周杰伦 青花瓷", 1),
    ("告白气球", "周杰伦", "周杰伦 告白气球", 1),
    ("简单爱", "周杰伦", "周杰伦 简单爱", 1),
    ("夜曲", "周杰伦", "周杰伦 夜曲", 1),
    ("听妈妈的话", "周杰伦", "周杰伦 听妈妈的话", 1),
    ("甜蜜蜜", "邓丽君", "邓丽君 甜蜜蜜", 1),
    ("月亮代表我的心", "邓丽君", "邓丽君 月亮代表我的心", 1),
    ("小幸运", "田馥甄", "田馥甄 小幸运", 1),
    ("童话", "光良", "光良 童话", 1),
    ("遇见", "孙燕姿", "孙燕姿 遇见", 1),
    ("天黑黑", "孙燕姿", "孙燕姿 天黑黑", 1),
    ("江南", "林俊杰", "林俊杰 江南", 1),
    ("可惜没如果", "林俊杰", "林俊杰 可惜没如果", 1),
    ("那些年", "胡夏", "胡夏 那些年", 1),
    ("小苹果", "筷子兄弟", "筷子兄弟 小苹果", 1),
    ("演员", "薛之谦", "薛之谦 演员", 1),
    ("光年之外", "邓紫棋", "邓紫棋 光年之外", 1),
    ("泡沫", "邓紫棋", "邓紫棋 泡沫", 1),
    ("起风了", "买辣椒也用券", "买辣椒也用券 起风了", 1),
    ("漂洋过海来看你", "李宗盛", "李宗盛 漂洋过海来看你", 1),
    ("平凡之路", "朴树", "朴树 平凡之路", 1),
    ("后来", "刘若英", "刘若英 后来", 1),
    ("倒带", "蔡依林", "蔡依林 倒带", 1),
    ("说爱你", "蔡依林", "蔡依林 说爱你", 1),
    ("勇气", "梁静茹", "梁静茹 勇气", 1),

    # ── 难度 2: 热门但不是人人都知道 ──
    ("花海", "周杰伦", "周杰伦 花海", 2),
    ("龙卷风", "周杰伦", "周杰伦 龙卷风", 2),
    ("反方向的钟", "周杰伦", "周杰伦 反方向的钟", 2),
    ("一路向北", "周杰伦", "周杰伦 一路向北", 2),
    ("修炼爱情", "林俊杰", "林俊杰 修炼爱情", 2),
    ("她说", "林俊杰", "林俊杰 她说", 2),
    ("关键词", "林俊杰", "林俊杰 关键词", 2),
    ("天后", "陈势安", "陈势安 天后", 2),
    ("有何不可", "许嵩", "许嵩 有何不可", 2),
    ("清明雨上", "许嵩", "许嵩 清明雨上", 2),
    ("半岛铁盒", "周杰伦", "周杰伦 半岛铁盒", 2),
    ("爱情转移", "陈奕迅", "陈奕迅 爱情转移", 2),
    ("十年", "陈奕迅", "陈奕迅 十年", 2),
    ("富士山下", "陈奕迅", "陈奕迅 富士山下", 2),
    ("红豆", "王菲", "王菲 红豆", 2),
    ("匆匆那年", "王菲", "王菲 匆匆那年", 2),
    ("错位时空", "艾辰", "艾辰 错位时空", 2),
    ("孤勇者", "陈奕迅", "陈奕迅 孤勇者", 2),
    ("大鱼", "周深", "周深 大鱼", 2),
    ("踏山河", "是七叔呢", "是七叔呢 踏山河", 2),
    ("万疆", "李玉刚", "李玉刚 万疆", 2),
    ("下山", "要不要买菜", "要不要买菜 下山", 2),
    ("少年", "梦然", "梦然 少年", 2),
    ("水星记", "郭顶", "郭顶 水星记", 2),
    ("成都", "赵雷", "赵雷 成都", 2),
    ("南山南", "马頔", "马頔 南山南", 2),
    ("消愁", "毛不易", "毛不易 消愁", 2),
    ("像鱼", "王贰浪", "王贰浪 像鱼", 2),

    # ── 难度 3: 小众/新歌/日韩ACG ──
    ("以父之名", "周杰伦", "周杰伦 以父之名", 3),
    ("止战之殇", "周杰伦", "周杰伦 止战之殇", 3),
    ("枫", "周杰伦", "周杰伦 枫", 3),
    ("我记得", "赵雷", "赵雷 我记得", 3),
    ("理想三旬", "陈鸿宇", "陈鸿宇 理想三旬", 3),
    ("执迷不悟", "小乐哥", "小乐哥 执迷不悟", 3),
    ("世间美好与你环环相扣", "柏松", "柏松 世间美好与你环环相扣", 3),
    ("沦陷", "王靖雯", "王靖雯不胖 沦陷", 3),
    ("白月光与朱砂痣", "大籽", "大籽 白月光与朱砂痣", 3),
    ("错季", "乔洋", "乔洋 错季", 3),
    ("黑人抬棺", "Tony Igy", "Tony Igy Astronomia", 3),
    ("打上花火", "米津玄师", "米津玄师 打上花火", 3),
    ("Lemon", "米津玄师", "米津玄师 Lemon", 3),
    ("残响散歌", "Aimer", "Aimer 残響散歌", 3),
    ("廻廻奇譚", "Eve", "Eve 廻廻奇譚", 3),
    ("红莲华", "LiSA", "LiSA 红莲华", 3),
    ("群青", "YOASOBI", "YOASOBI 群青", 3),
    ("夜に駆ける", "YOASOBI", "YOASOBI 夜に駆ける", 3),
    ("うっせぇわ", "Ado", "Ado うっせぇわ", 3),
    ("花に亡霊", "ヨルシカ", "ヨルシカ 花に亡霊", 3),
]

# 答案匹配用的别名映射
SONG_ALIASES = {
    "晴天": ["晴天", "qingtian"],
    "稻香": ["稻香", "daoxiang"],
    "七里香": ["七里香", "qilixiang"],
    "告白气球": ["告白气球", "gaobaiqiqiu"],
    "青花瓷": ["青花瓷", "qinghuaci"],
    "小幸运": ["小幸运", "xiaoxingyun"],
    "童话": ["童话", "tonghua"],
    "遇见": ["遇见", "yujian"],
    "江南": ["江南", "jiangnan"],
    "演员": ["演员", "yanyuan"],
    "红莲华": ["红莲华", "gurenge"],
    "夜に駆ける": ["夜に駆ける", "夜奔", "yoru ni kakeru", "racing into the night"],
    "群青": ["群青", "gunjou"],
    "Lemon": ["lemon", "柠檬"],
}

# 难度对应的播放时长 (秒)
DIFFICULTY_DURATION = {1: 45, 2: 40, 3: 35}
DIFFICULTY_NAMES = {1: "简单 🟢", 2: "中等 🟡", 3: "困难 🔴"}
DIFFICULTY_POINTS = {1: 1, 2: 2, 3: 3}


def normalize(text: str) -> str:
    """标准化文本用于匹配"""
    return normalize_answer_text(text)


def check_answer(guess: str, song_name: str, artist: str) -> bool:
    """检查猜测是否正确"""
    return check_guess_answer(guess, song_name, artist)


class GuessGame:
    """一局猜歌游戏的状态"""

    def __init__(
        self,
        channel: discord.TextChannel,
        voice_channel: discord.VoiceChannel,
        rounds: int = 5,
        difficulty: int = 0,  # 0=混合, 1-3=指定难度
        starter: discord.Member = None,
    ):
        self.channel = channel
        self.voice_channel = voice_channel
        self.rounds = rounds
        self.difficulty = difficulty
        self.starter = starter
        self.current_round = 0
        self.current_song: tuple | None = None  # (name, artist, query, diff)
        self.scores: dict[int, int] = defaultdict(int)  # user_id -> score
        self.player_names: dict[int, str] = {}  # user_id -> display_name
        self.answered = False
        self.active = True
        self.used_songs: set[str] = set()  # 避免重复
        self.saved_music_state: dict | None = None

    def pick_song(self) -> tuple:
        """选一首还没用过的歌"""
        if self.difficulty > 0:
            pool = [s for s in SONG_DATABASE if s[3] == self.difficulty
                    and s[0] not in self.used_songs]
        else:
            pool = [s for s in SONG_DATABASE if s[0] not in self.used_songs]

        if not pool:
            # 如果用完了就重置
            self.used_songs.clear()
            pool = (
                [s for s in SONG_DATABASE if s[3] == self.difficulty]
                if self.difficulty > 0 else list(SONG_DATABASE)
            )

        song = random.choice(pool)
        self.used_songs.add(song[0])
        return song

    def get_scoreboard(self) -> str:
        """生成积分排行榜"""
        if not self.scores:
            return "还没有人答对过 😔"

        sorted_scores = sorted(
            self.scores.items(), key=lambda x: x[1], reverse=True
        )
        lines = []
        medals = ["🥇", "🥈", "🥉"]
        for i, (uid, score) in enumerate(sorted_scores):
            name = self.player_names.get(uid, "???")
            medal = medals[i] if i < 3 else f"`{i+1}.`"
            lines.append(f"{medal} **{name}** — {score} 分")
        return "\n".join(lines)


class MusicGame(commands.Cog, name="🎮 猜歌游戏"):
    """猜歌游戏相关命令"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.games: dict[int, GuessGame] = {}  # guild_id -> game

    @commands.hybrid_command(
        name="猜歌",
        aliases=["guess", "猜歌游戏", "开始猜歌"],
        help="开始一局猜歌游戏",
    )
    @app_commands.describe(
        rounds="游戏轮数 (默认5轮)",
        difficulty="难度: 1=简单 2=中等 3=困难 0=混合 (默认0)",
    )
    async def start_game(
        self,
        ctx: commands.Context,
        rounds: int = 5,
        difficulty: int = 0,
    ):
        # 检查用户在语音频道
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.send("❌ 你需要先加入一个语音频道！")

        guild_id = ctx.guild.id
        if guild_id in self.games and self.games[guild_id].active:
            return await ctx.send("❌ 当前已有一局游戏进行中，用 `！结束猜歌` 结束")

        if not 1 <= rounds <= 20:
            return await ctx.send("❌ 轮数范围: 1-20")
        if difficulty not in (0, 1, 2, 3):
            return await ctx.send("❌ 难度: 0=混合, 1=简单, 2=中等, 3=困难")

        # 创建游戏
        voice_channel = ctx.author.voice.channel
        game = GuessGame(
            channel=ctx.channel,
            voice_channel=voice_channel,
            rounds=rounds,
            difficulty=difficulty,
            starter=ctx.author,
        )
        self.games[guild_id] = game

        # 加入语音
        vc = ctx.voice_client
        if not vc:
            vc = await voice_channel.connect()
        elif vc.channel != voice_channel:
            await vc.move_to(voice_channel)

        await self._claim_music_player(ctx, game, vc)

        diff_name = DIFFICULTY_NAMES.get(difficulty, "混合 🌈")
        embed = discord.Embed(
            title="🎮 猜歌游戏开始！",
            description=(
                f"**{ctx.author.display_name}** 发起了猜歌游戏\n\n"
                f"📋 轮数: **{rounds}** 轮\n"
                f"🎯 难度: **{diff_name}**\n"
                f"⏱️ 每轮片段: **35-45秒**（难度越高越短）\n"
                "🎧 长歌曲会从中段开始播放，避开片头和过长前奏\n\n"
                "🎵 在语音频道播放歌曲片段\n"
                "💬 在文字频道打字猜歌名\n"
                "🏆 猜对得分，最终看谁分最高！\n\n"
                "*游戏即将开始...*"
            ),
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed, silent=True)
        await asyncio.sleep(3)

        # 开始游戏循环
        try:
            await self._game_loop(ctx, game, vc)
        except Exception:
            game.active = False
            self.games.pop(guild_id, None)
            await self._restore_music_player(ctx, game, vc)
            raise

    async def _game_loop(
        self,
        ctx: commands.Context,
        game: GuessGame,
        vc: discord.VoiceClient,
    ):
        """游戏主循环"""
        for round_num in range(1, game.rounds + 1):
            if not game.active:
                break

            game.current_round = round_num
            game.answered = False

            # 选歌
            song = game.pick_song()
            game.current_song = song
            song_name, artist, query, diff = song

            diff_name = DIFFICULTY_NAMES.get(diff, "?")
            points = DIFFICULTY_POINTS.get(diff, 1)

            # 搜索音频
            await ctx.send(
                f"🎵 **第 {round_num}/{game.rounds} 轮** — "
                f"难度: {diff_name} (+{points}分)\n"
                "正在加载歌曲...",
                silent=True,
            )

            info, is_bili = await self._search_song(
                query, user_id=ctx.author.id
            )
            if not info:
                await ctx.send(
                    "⚠️ B站和备用音源都无法加载这首歌，跳到下一轮。\n"
                    "可尝试重新 `！绑定b站` 更新 cookies。",
                    silent=True,
                )
                continue

            # 播放片段
            audio_url = info.get("url")
            if not audio_url:
                await ctx.send(
                    "⚠️ 无法获取音频，跳到下一轮...", silent=True
                )
                continue

            requested_duration = DIFFICULTY_DURATION.get(diff, 40)
            start_offset, duration = calculate_clip_window(
                info.get("duration"), requested_duration
            )
            started = await self._play_game_audio(
                vc,
                audio_url,
                duration=duration,
                start_offset=start_offset,
                is_bili=is_bili,
            )
            if not started and is_bili:
                await ctx.send("🔁 B站音频流启动失败，正在尝试备用音源...", silent=True)
                info, is_bili = await self._search_song(
                    query, user_id=ctx.author.id, skip_bili=True
                )
                audio_url = info.get("url") if info else None
                start_offset, duration = calculate_clip_window(
                    info.get("duration") if info else None,
                    requested_duration,
                )
                started = bool(audio_url) and await self._play_game_audio(
                    vc,
                    audio_url,
                    duration=duration,
                    start_offset=start_offset,
                    is_bili=is_bili,
                )

            if not started:
                await ctx.send(
                    "⚠️ 音源已找到，但 FFmpeg 没有成功开始播放，已跳到下一轮。\n"
                    "请用 `！诊断` 检查 FFmpeg 和语音依赖。",
                    silent=True,
                )
                continue

            await ctx.send(
                f"🔊 **听歌中...** 你有 **{duration}秒** 猜歌名！\n"
                + (f"🎧 本轮从歌曲约 **{start_offset}秒** 处开始播放\n" if start_offset else "")
                + f"💡 提示: 这是一首{'华语' if diff < 3 else ''}歌曲",
                silent=True,
            )

            # 等待答案，超时时间与实际片段长度一致。
            try:
                msg = await self.bot.wait_for(
                    "message",
                    timeout=float(duration),
                    check=lambda m: (
                        m.channel == ctx.channel
                        and not m.author.bot
                        and game.active
                        and not game.answered
                        and check_answer(m.content, song_name, artist)
                    ),
                )
                # 有人猜对了
                game.answered = True
                if vc.is_playing():
                    vc.stop()

                game.scores[msg.author.id] += points
                game.player_names[msg.author.id] = msg.author.display_name

                embed = discord.Embed(
                    title="✅ 答对了！",
                    description=(
                        f"🎉 **{msg.author.display_name}** 猜对了！"
                        f" (+{points}分)\n\n"
                        f"🎵 **{song_name}** — {artist}\n"
                        f"📊 当前得分: **{game.scores[msg.author.id]}** 分"
                    ),
                    color=discord.Color.green(),
                )
                await ctx.send(embed=embed, silent=True)

            except asyncio.TimeoutError:
                if not game.active:
                    break
                # 没人猜对
                if vc.is_playing():
                    vc.stop()

                embed = discord.Embed(
                    title="⏰ 时间到！",
                    description=(
                        f"没人猜到！答案是:\n\n"
                        f"🎵 **{song_name}** — {artist}"
                    ),
                    color=discord.Color.red(),
                )
                await ctx.send(embed=embed, silent=True)

            # 轮间间隔
            if round_num < game.rounds and game.active:
                await asyncio.sleep(3)

        # 游戏结束
        if game.active:
            await self._end_game(ctx, game, vc)

    async def _end_game(
        self,
        ctx: commands.Context,
        game: GuessGame,
        vc: discord.VoiceClient,
    ):
        """结束游戏，显示排行榜"""
        game.active = False
        guild_id = ctx.guild.id
        if guild_id in self.games:
            del self.games[guild_id]

        scoreboard = game.get_scoreboard()

        # 找出冠军
        winner_text = ""
        if game.scores:
            max_score = max(game.scores.values())
            winners = [
                game.player_names[uid]
                for uid, s in game.scores.items()
                if s == max_score
            ]
            if len(winners) == 1:
                winner_text = f"\n\n👑 本局冠军: **{winners[0]}**！"
            else:
                winner_text = (
                    f"\n\n👑 并列冠军: **{'、'.join(winners)}**！"
                )

        embed = discord.Embed(
            title="🏆 猜歌游戏结束！",
            description=f"{scoreboard}{winner_text}",
            color=discord.Color.gold(),
        )
        embed.set_footer(
            text=f"共 {game.rounds} 轮 | 发起者: {game.starter.display_name}"
        )
        await ctx.send(embed=embed, silent=True)

        resumed = await self._restore_music_player(ctx, game, vc)
        if resumed:
            await ctx.send("▶️ 猜歌前的播放队列已恢复。", silent=True)
        elif vc and vc.is_connected():
            await vc.disconnect()

    @commands.hybrid_command(
        name="结束猜歌",
        aliases=["stopgame", "endgame", "游戏结束"],
        help="结束当前的猜歌游戏",
    )
    async def stop_game(self, ctx: commands.Context):
        guild_id = ctx.guild.id
        game = self.games.get(guild_id)
        if not game or not game.active:
            return await ctx.send("❌ 当前没有进行中的猜歌游戏")

        game.active = False
        vc = ctx.voice_client
        if vc and vc.is_playing():
            vc.stop()

        await self._end_game(ctx, game, vc)

    @commands.hybrid_command(
        name="猜歌分数",
        aliases=["gamescore", "游戏分数", "猜歌排行"],
        help="查看当前猜歌游戏的积分",
    )
    async def game_score(self, ctx: commands.Context):
        guild_id = ctx.guild.id
        game = self.games.get(guild_id)
        if not game or not game.active:
            return await ctx.send("❌ 当前没有进行中的猜歌游戏")

        embed = discord.Embed(
            title=f"📊 猜歌积分 (第 {game.current_round}/{game.rounds} 轮)",
            description=game.get_scoreboard(),
            color=discord.Color.blue(),
        )
        await ctx.send(embed=embed, silent=True)

    def _music_cog(self):
        return self.bot.get_cog("🎵 音乐")

    async def _claim_music_player(
        self,
        ctx: commands.Context,
        game: GuessGame,
        vc: discord.VoiceClient,
    ):
        """Temporarily hand the shared voice client from music to the game."""
        music = self._music_cog()
        if not music:
            return

        player = music.get_player(ctx.guild.id)
        pending = []
        if player.current:
            pending.append(player.current)
        pending.extend(player.queue)
        game.saved_music_state = {
            "songs": pending,
            "volume": player.volume,
            "auto_lyrics": player.auto_lyrics,
            "loop": player.loop,
            "loop_queue": player.loop_queue,
        }

        player.external_control = True
        player.queue.clear()
        player.current = None
        player.loop = False
        player.loop_queue = False
        if vc.is_playing() or vc.is_paused():
            player.intentional_stop = True
            vc.stop()
            await asyncio.sleep(0.25)

    async def _restore_music_player(
        self,
        ctx: commands.Context,
        game: GuessGame,
        vc: discord.VoiceClient,
    ) -> bool:
        music = self._music_cog()
        state = game.saved_music_state
        game.saved_music_state = None
        if not music or not state:
            return False

        player = music.get_player(ctx.guild.id)
        player.external_control = False
        player.volume = state["volume"]
        player.auto_lyrics = state["auto_lyrics"]
        player.loop = state["loop"]
        player.loop_queue = state["loop_queue"]
        player.current = None
        player.queue.clear()
        player.queue.extend(state["songs"])
        if not player.queue or not vc or not vc.is_connected():
            return False

        await music._async_play_next(ctx)
        return True

    @staticmethod
    async def _play_game_audio(
        vc: discord.VoiceClient,
        audio_url: str,
        *,
        duration: int,
        start_offset: int = 0,
        is_bili: bool,
    ) -> bool:
        """Start one bounded clip and verify FFmpeg stays alive briefly."""
        options = (BILI_FFMPEG_OPTIONS if is_bili else FFMPEG_OPTIONS).copy()
        if start_offset > 0:
            options["before_options"] = (
                f"{options.get('before_options', '')} -ss {start_offset}"
            ).strip()
        options["options"] = f"-vn -t {duration}"
        finished = asyncio.Event()
        loop = asyncio.get_running_loop()

        def after_playback(error):
            if error:
                print(f"猜歌音频流结束: {error}")
            loop.call_soon_threadsafe(finished.set)

        try:
            if vc.is_playing() or vc.is_paused():
                vc.stop()
                await asyncio.sleep(0.15)
            source = discord.FFmpegPCMAudio(audio_url, **options)
            source = discord.PCMVolumeTransformer(source, volume=0.5)
            vc.play(source, after=after_playback)
            await asyncio.sleep(1.0)
            return vc.is_playing() and not finished.is_set()
        except Exception as exc:
            print(f"猜歌播放出错: {exc}")
            return False

    async def _search_song(
        self,
        query: str,
        *,
        user_id: int | None = None,
        skip_bili: bool = False,
    ) -> tuple[dict | None, bool]:
        """Prefer the normal Bilibili resolver, then fall back to YouTube."""
        music = self._music_cog()
        if music and not skip_bili:
            info = await music._search(query, bili_mode=True, user_id=user_id)
            if info and info.get("url"):
                return info, True

        if music:
            info = await music._search(query, bili_mode=False)
            return (info, False) if info and info.get("url") else (None, False)

        try:
            info = await extract_first(query, GAME_YDL_OPTIONS)
            return (info, False) if info and info.get("url") else (None, False)
        except Exception as e:
            print(f"猜歌搜索出错: {e}")
            return None, False


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicGame(bot))
