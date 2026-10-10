"""
Discord 音乐机器人 - 音乐功能模块
支持: YouTube / Bilibili / 网易云 搜索播放, 歌单导入, 播放队列, 音量控制, 循环播放等
"""
import asyncio
import datetime
import io
import json
import math
import os
import re
import time
from collections import deque

import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp

from cogs.lyrics_utils import extract_lyrics_candidates
from cogs.playlist_parsers import (
    BILI_URL_PATTERN,
    clean_search_query,
    extract_bili_collection_info,
    extract_bili_fav_id,
    extract_netease_id,
    is_bili_url,
)
from cogs.services.cookies import parse_netscape_cookie_file
from cogs.services.cookies import replace_cookie_file, validate_bili_cookie_text
from cogs.services.media_search import extract_first
from cogs.services.lyrics import clean_lyric_text, fetch_lrclib_lyrics
from cogs.services.netease import fetch_playlist as fetch_netease_playlist
from cogs.services.http import request_json
from cogs.services.bilibili import (
    fetch_collection_entries,
    fetch_favorite_entries,
)
from cogs.services.queue_snapshot import build_snapshot, validate_snapshot
from cogs.services.queue_snapshot import (
    append_named_queue_record,
    delete_named_queue,
    empty_snapshot,
    list_named_queues,
    load_named_queue,
    records_from_snapshot,
    sanitize_queue_name,
    save_named_queue,
    song_to_record,
)

# ─── yt-dlp 配置 ───
YDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
    "extract_flat": False,
    "socket_timeout": 30,
}

# B站专用配置
BILI_YDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "source_address": "0.0.0.0",
    "extract_flat": False,
    "socket_timeout": 30,
    "http_headers": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.bilibili.com/",
    },
}

FFMPEG_OPTIONS = {
    "before_options": (
        "-nostdin -reconnect 1 -reconnect_streamed 1 "
        "-reconnect_on_network_error 1 -reconnect_on_http_error 4xx,5xx "
        "-reconnect_delay_max 10"
    ),
    "options": "-vn",
}

# B站专用 FFmpeg 配置 (需要带 Referer 和 User-Agent 头, 否则被CDN拒绝)
BILI_FFMPEG_OPTIONS = {
    "before_options": (
        '-nostdin -reconnect 1 -reconnect_streamed 1 '
        '-reconnect_on_network_error 1 -reconnect_on_http_error 4xx,5xx '
        '-reconnect_delay_max 10 '
        '-user_agent "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" '
        '-headers "Referer: https://www.bilibili.com/\r\n"'
    ),
    "options": "-vn",
}

# ─── 音效滤镜 ───
AUDIO_FILTERS = {
    "低音炮": "bass=g=10,dynaudnorm=f=200",
    "夜核": "asetrate=44100*1.3,aresample=44100",
    "慢放": "atempo=0.75",
    "加速": "atempo=1.5",
    "8D": "apulsator=hz=0.125",
    "回声": "aecho=0.8:0.9:500:0.3",
    "空灵": "aecho=0.8:0.88:60:0.4,treble=g=3",
}

# ─── Cookies 配置 (每个用户独立) ───
COOKIES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cookies"
)
os.makedirs(COOKIES_DIR, exist_ok=True)


def get_user_cookies_path(user_id: int) -> str:
    """获取指定用户的 cookies 文件路径"""
    return os.path.join(COOKIES_DIR, f"{user_id}.txt")


def user_has_cookies(user_id: int) -> bool:
    """检查用户是否已绑定 cookies"""
    return os.path.exists(get_user_cookies_path(user_id))


class Song:
    """表示一首歌曲 (支持懒搜索: 歌单歌曲在播放前才搜索解析)"""

    def __init__(
        self,
        source_url: str | None,
        title: str,
        webpage_url: str,
        duration: int,
        thumbnail: str,
        requester: discord.Member,
        is_bili: bool = False,
        search_query: str | None = None,
    ):
        self.source_url = source_url
        self.title = title
        self.webpage_url = webpage_url
        self.duration = duration
        self.thumbnail = thumbnail
        self.requester = requester
        self.is_bili = is_bili
        self.search_query = search_query  # 歌单歌曲的懒搜索关键词

    @property
    def is_resolved(self) -> bool:
        """是否已解析出音频URL"""
        return self.source_url is not None

    @property
    def ffmpeg_options(self) -> dict:
        """根据来源返回对应的 FFmpeg 配置"""
        return BILI_FFMPEG_OPTIONS if self.is_bili else FFMPEG_OPTIONS

    @property
    def duration_str(self) -> str:
        if not self.duration:
            return "未知"
        return str(datetime.timedelta(seconds=self.duration))

    def create_embed(self, status="正在播放 🎶"):
        if self.webpage_url:
            description = f"[**{self.title}**]({self.webpage_url})"
        else:
            description = f"**{self.title}**"
        embed = discord.Embed(
            title=status,
            description=description,
            color=discord.Color.blurple(),
        )
        embed.add_field(name="时长", value=self.duration_str, inline=True)
        embed.add_field(name="请求者", value=self.requester.mention, inline=True)
        if self.thumbnail:
            embed.set_thumbnail(url=self.thumbnail)
        return embed


class MusicPlayer:
    """每个服务器的音乐播放器"""

    def __init__(self):
        self.queue: deque[Song] = deque()
        self.current: Song | None = None
        self.volume: float = 0.5
        self.loop: bool = False
        self.loop_queue: bool = False
        self.audio_filter: str | None = None  # 当前音效滤镜名称
        self.replay_current: bool = False  # 切换滤镜时重播当前歌曲
        self.started_at: float | None = None
        self.stream_retries: int = 0
        self.intentional_stop: bool = False
        self.external_control: bool = False
        self.auto_lyrics: bool = False

    def clear(self):
        self.queue.clear()
        self.current = None
        self.loop = False
        self.loop_queue = False
        self.audio_filter = None
        self.replay_current = False
        self.started_at = None
        self.stream_retries = 0
        self.intentional_stop = False
        self.external_control = False
        self.auto_lyrics = False


class PlaylistPager(discord.ui.View):
    """Button-paged view for a saved playlist."""

    PAGE_SIZE = 10

    def __init__(self, name: str, records: list[dict], requester_id: int):
        super().__init__(timeout=180)
        self.name = name
        self.records = records
        self.requester_id = requester_id
        self.page = 0
        self.message: discord.Message | None = None
        self._sync_buttons()

    @property
    def page_count(self) -> int:
        return max(1, math.ceil(len(self.records) / self.PAGE_SIZE))

    def create_embed(self) -> discord.Embed:
        start = self.page * self.PAGE_SIZE
        page_records = self.records[start : start + self.PAGE_SIZE]
        lines = []
        for offset, record in enumerate(page_records, start=start + 1):
            duration = record.get("duration", 0)
            duration_text = (
                str(datetime.timedelta(seconds=duration)) if duration else "未知"
            )
            title = record.get("title", "未知歌曲")
            url = record.get("webpage_url", "")
            title_text = f"[{title}]({url})" if url else title
            lines.append(f"`{offset}.` {title_text} · `{duration_text}`")

        total_duration = sum(
            record.get("duration", 0) or 0 for record in self.records
        )
        embed = discord.Embed(
            title=f"歌单 · {self.name}",
            description="\n".join(lines) or "这个歌单还是空的。",
            color=discord.Color.blurple(),
        )
        total_text = (
            str(datetime.timedelta(seconds=total_duration))
            if total_duration
            else "未知"
        )
        embed.add_field(name="歌曲", value=str(len(self.records)), inline=True)
        embed.add_field(name="总时长", value=total_text, inline=True)
        embed.set_footer(text=f"第 {self.page + 1}/{self.page_count} 页")
        return embed

    def _sync_buttons(self) -> None:
        self.previous_page.disabled = self.page <= 0
        self.next_page.disabled = self.page >= self.page_count - 1

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.requester_id:
            return True
        await interaction.response.send_message(
            "只有打开这个歌单的用户可以翻页。", ephemeral=True
        )
        return False

    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.secondary)
    async def previous_page(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.page -= 1
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.secondary)
    async def next_page(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.page += 1
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class Music(commands.Cog, name="🎵 音乐"):
    """播放音乐的所有命令"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.players: dict[int, MusicPlayer] = {}
        self.skip_votes: dict[int, set[int]] = {}
        self.playlist_sessions: set[tuple[int, int]] = set()

    def get_player(self, guild_id: int) -> MusicPlayer:
        if guild_id not in self.players:
            self.players[guild_id] = MusicPlayer()
        return self.players[guild_id]

    def _song_from_record(
        self,
        record: dict,
        requester: discord.Member,
        *,
        force_resolve: bool = False,
    ) -> Song:
        webpage_url = record.get("webpage_url", "")
        title = record.get("title", "未知")
        return Song(
            source_url=None if force_resolve else record.get("source_url"),
            title=title,
            webpage_url=webpage_url,
            duration=record.get("duration", 0),
            thumbnail=record.get("thumbnail", ""),
            requester=requester,
            is_bili=bool(record.get("is_bili", False) or is_bili_url(webpage_url)),
            search_query=(
                record.get("search_query") or webpage_url or title
            ),
        )

    def _append_records_to_queue(
        self,
        player: MusicPlayer,
        records: list[dict],
        requester: discord.Member,
        *,
        force_resolve: bool = False,
    ) -> int:
        for record in records:
            player.queue.append(
                self._song_from_record(
                    record, requester, force_resolve=force_resolve
                )
            )
        return len(records)

    async def _read_queue_attachment(self, ctx: commands.Context) -> dict:
        if not ctx.message.attachments:
            raise ValueError("请附加一个由 `！导出队列` 生成的 JSON 文件")

        attachment = ctx.message.attachments[0]
        if not attachment.filename.lower().endswith(".json"):
            raise ValueError("队列文件必须是 JSON")

        raw = await attachment.read()
        payload = json.loads(raw.decode("utf-8"))
        validate_snapshot(payload)
        return payload

    async def _save_current_queue(
        self, ctx: commands.Context, name: str
    ) -> str | None:
        player = self.get_player(ctx.guild.id)
        if not player.current and not player.queue:
            await ctx.send("📭 播放队列为空，没什么可保存的。")
            return None

        payload = build_snapshot(player)
        path = save_named_queue(ctx.guild.id, name, payload)
        return path.stem

    async def _resolve_playlist_record(
        self, query: str, requester_id: int
    ) -> dict | None:
        """Resolve a durable playlist record through the normal player search."""
        info, is_bili, _ = await self._search_music_sources(
            query, user_id=requester_id
        )
        if not info:
            return None
        webpage_url = info.get("webpage_url", "")
        return {
            "source_url": None,
            "title": info.get("title", query),
            "webpage_url": webpage_url,
            "duration": info.get("duration", 0),
            "thumbnail": info.get("thumbnail", ""),
            "is_bili": is_bili or self._is_bili_url(webpage_url),
            "search_query": webpage_url or query,
        }

    # ═══════════════════════════════════════
    # 工具方法
    # ═══════════════════════════════════════

    @staticmethod
    def _is_bili_url(query: str) -> bool:
        """判断是否是B站链接"""
        return is_bili_url(query)

    @staticmethod
    async def _search(
        query: str, bili_mode: bool = False, user_id: int | None = None
    ) -> dict | None:
        """用 yt-dlp 搜索/解析音频"""
        is_bili = bili_mode or bool(BILI_URL_PATTERN.search(query))
        options = BILI_YDL_OPTIONS.copy() if is_bili else YDL_OPTIONS.copy()

        # 使用该用户的 cookies（如果有）
        if is_bili and user_id and user_has_cookies(user_id):
            options["cookiefile"] = get_user_cookies_path(user_id)

        # B站关键词搜索: 使用 bilisearch
        if bili_mode and not query.startswith(("http://", "https://")):
            query = f"bilisearch:{query}"

        try:
            return await extract_first(query, options)
        except Exception as e:
            print(f"搜索出错: {e}")
            return None

    async def _search_music_sources(
        self,
        query: str,
        *,
        user_id: int | None = None,
        prefer_bili: bool = False,
    ) -> tuple[dict | None, bool, str]:
        """Resolve a URL or search keywords with bounded source fallback."""
        is_url = query.strip().startswith(("http://", "https://"))
        if self._is_bili_url(query):
            info = await self._search(query, bili_mode=True, user_id=user_id)
            return info, True, "B站"
        if is_url:
            info = await self._search(query)
            return info, False, "链接"
        if prefer_bili:
            info = await self._search(query, bili_mode=True, user_id=user_id)
            return info, True, "B站"

        info = await self._search(query)
        if info:
            return info, False, "YouTube"
        info = await self._search(query, bili_mode=True, user_id=user_id)
        return info, bool(info), "B站" if info else "YouTube / B站"

    def _create_source(
        self, song: Song, player: MusicPlayer
    ) -> discord.PCMVolumeTransformer:
        """创建音频源（自动应用滤镜设置）"""
        base_opts = song.ffmpeg_options.copy()
        # 应用音效滤镜
        if player.audio_filter and player.audio_filter in AUDIO_FILTERS:
            filter_str = AUDIO_FILTERS[player.audio_filter]
            base_opts["options"] = f'-vn -af "{filter_str}"'
        source = discord.FFmpegPCMAudio(song.source_url, **base_opts)
        return discord.PCMVolumeTransformer(source, volume=player.volume)

    def _start_playback(
        self,
        ctx: commands.Context,
        vc: discord.VoiceClient,
        song: Song,
        player: MusicPlayer,
    ):
        """Start playback and record timing for reconnect decisions."""
        source = self._create_source(song, player)
        player.started_at = time.monotonic()
        vc.play(source, after=lambda e: self._play_next(ctx, e))

    def _play_next(self, ctx: commands.Context, error: Exception | None = None):
        """播放队列中的下一首 (after 回调入口，委托给异步方法)"""
        asyncio.run_coroutine_threadsafe(
            self._async_play_next(ctx, playback_error=error), self.bot.loop
        )

    def _ended_too_early(self, player: MusicPlayer) -> bool:
        song = player.current
        if not song or not song.duration or not player.started_at:
            return False
        elapsed = time.monotonic() - player.started_at
        return song.duration >= 180 and elapsed < song.duration - 30

    async def _retry_current_stream(
        self,
        ctx: commands.Context,
        vc: discord.VoiceClient,
        player: MusicPlayer,
        reason: str,
    ) -> bool:
        song = player.current
        if not song or player.stream_retries >= 2:
            return False

        player.stream_retries += 1
        requester_id = getattr(song.requester, "id", None)
        query = song.webpage_url or song.search_query or song.title
        await ctx.send(
            f"🔁 当前音频流中断，正在重新连接 "
            f"({player.stream_retries}/2): **{song.title}**"
        )

        info = await self._search(
            query,
            bili_mode=song.is_bili,
            user_id=requester_id,
        )
        if not info or not info.get("url"):
            print(f"重连失败 ({reason}): {song.title}")
            return False

        song.source_url = info.get("url")
        song.webpage_url = info.get("webpage_url", song.webpage_url)
        song.duration = info.get("duration", song.duration)
        song.thumbnail = info.get("thumbnail", song.thumbnail)
        song.title = info.get("title", song.title)
        self._start_playback(ctx, vc, song, player)
        return True

    async def _async_play_next(
        self,
        ctx: commands.Context,
        skip_count: int = 0,
        playback_error: Exception | None = None,
    ):
        """异步播放下一首 (支持歌单歌曲的懒搜索解析)"""
        player = self.get_player(ctx.guild.id)
        vc = ctx.voice_client

        if not vc or not vc.is_connected():
            return

        # Guess-song mode temporarily owns the shared voice client.
        if player.external_control:
            return

        # 滤镜切换: 重播当前歌曲
        if player.replay_current and player.current and player.current.is_resolved:
            player.replay_current = False
            player.intentional_stop = False
            self._start_playback(ctx, vc, player.current, player)
            filter_label = player.audio_filter or "原声"
            await ctx.send(
                embed=player.current.create_embed(f"🎛️ 滤镜: {filter_label}")
            )
            return

        if player.intentional_stop:
            player.intentional_stop = False
        elif player.current and (
            playback_error is not None or self._ended_too_early(player)
        ):
            reason = str(playback_error) if playback_error else "early EOF"
            print(f"播放中断: {reason}")
            if await self._retry_current_stream(ctx, vc, player, reason):
                return
            await ctx.send("⚠️ 当前曲目重连失败，已跳过。")

        # 连续搜索失败保护
        if skip_count > 5:
            await ctx.send("⚠️ 连续多首歌无法搜索到，停止播放。")
            player.current = None
            return

        # 循环当前曲目
        if player.loop and player.current and player.current.is_resolved:
            self._start_playback(ctx, vc, player.current, player)
            return

        # 循环队列: 把当前歌曲放回队尾
        if player.loop_queue and player.current:
            player.queue.append(player.current)

        if player.queue:
            song = player.queue.popleft()

            # 懒搜索: 歌单中的歌曲在播放前才搜索解析
            if not song.is_resolved:
                await ctx.send(f"🔍 正在搜索: **{song.title}**")
                requester_id = getattr(song.requester, "id", None)
                info, resolved_bili, _ = await self._search_music_sources(
                    song.search_query or song.title,
                    user_id=requester_id,
                    prefer_bili=song.is_bili,
                )
                if info:
                    song.is_bili = resolved_bili
                    song.source_url = info.get("url")
                    song.webpage_url = info.get("webpage_url", "")
                    song.duration = info.get("duration", 0)
                    song.thumbnail = info.get("thumbnail", "")
                    song.title = info.get("title", song.title)
                else:
                    if song.is_bili:
                        if requester_id and not user_has_cookies(requester_id):
                            await ctx.send(
                                "⚠️ B站搜索失败。你还没有绑定 B站 cookies，"
                                "可用 `！绑定b站` 上传 cookies.txt 后再试。"
                            )
                        else:
                            await ctx.send(
                                "⚠️ B站搜索失败。视频可能存在，但 B站返回了风控/412；"
                                "请尝试重新 `！绑定b站` 更新 cookies。"
                            )
                    await ctx.send(f"⚠️ 搜索不到: **{song.title}**，已跳过")
                    await self._async_play_next(ctx, skip_count + 1)
                    return

            player.current = song
            self.skip_votes.pop(ctx.guild.id, None)
            player.stream_retries = 0
            self._start_playback(ctx, vc, song, player)
            await ctx.send(embed=song.create_embed())
            if player.auto_lyrics:
                await self._send_auto_lyrics(ctx, song)
        else:
            player.current = None
            player.auto_lyrics = False
            await self._auto_disconnect(ctx)

    async def _auto_disconnect(self, ctx: commands.Context):
        """3 分钟无播放后自动断开"""
        await asyncio.sleep(180)
        vc = ctx.voice_client
        player = self.get_player(ctx.guild.id)
        if vc and vc.is_connected() and not vc.is_playing():
            player.clear()
            await vc.disconnect()
            await ctx.send("⏹️ 长时间无活动，已自动断开连接。")

    @staticmethod
    def _ensure_voice():
        """装饰器: 确保用户在语音频道中"""
        async def predicate(ctx: commands.Context) -> bool:
            if not ctx.author.voice or not ctx.author.voice.channel:
                await ctx.send("❌ 你需要先加入一个语音频道！", silent=True)
                return False
            return True
        return commands.check(predicate)

    # ═══════════════════════════════════════
    # 歌单辅助方法
    # ═══════════════════════════════════════

    @staticmethod
    def _extract_bili_fav_id(url: str) -> str | None:
        """从B站收藏夹URL中提取 media_id"""
        return extract_bili_fav_id(url)

    @staticmethod
    def _extract_bili_collection_info(url: str) -> dict | None:
        """
        从B站合集/系列URL中提取 mid 和 season_id 或 series_id
        支持:
          - https://space.bilibili.com/{mid}/lists/{sid}?type=season (新版)
          - https://space.bilibili.com/{mid}/lists/{sid}?type=series (新版)
          - https://space.bilibili.com/{mid}/lists/{sid} (默认当合集)
          - https://space.bilibili.com/{mid}/channel/collectiondetail?sid={sid}
          - https://space.bilibili.com/{mid}/channel/seriesdetail?sid={sid}
          - https://www.bilibili.com/list/{mid}?sid={sid}&stype=season
        """
        return extract_bili_collection_info(url)

    async def _fetch_bili_collection(
        self, url: str, user_id: int | None = None
    ) -> tuple[str, list[dict]]:
        """
        获取B站合集/系列的视频列表
        返回 (合集名称, [{title, url, duration}])
        """
        loop = asyncio.get_event_loop()
        collection_info = self._extract_bili_collection_info(url)

        def _fetch():
            cookies = {}
            if user_id and user_has_cookies(user_id):
                cookie_path = get_user_cookies_path(user_id)
                try:
                    cookies = parse_netscape_cookie_file(cookie_path)
                except Exception:
                    pass
            return fetch_collection_entries(collection_info, cookies)

        try:
            return await loop.run_in_executor(None, _fetch)
        except Exception as e:
            print(f"B站合集提取出错: {e}")
            return "", []

    @staticmethod
    def _extract_netease_id(query: str) -> str | None:
        """从链接或纯ID中提取网易云歌单ID"""
        return extract_netease_id(query)

    @staticmethod
    async def _fetch_netease_playlist(playlist_id: str) -> tuple[str, list[dict]]:
        """获取网易云歌单详情，返回 (歌单名, [{name, artist, query}])"""
        return await fetch_netease_playlist(playlist_id)

    async def _extract_bili_playlist(
        self, url: str, user_id: int | None = None
    ) -> list[dict]:
        """提取B站播放列表/收藏夹中的所有视频信息"""
        loop = asyncio.get_event_loop()

        # 尝试从URL中提取收藏夹ID，使用B站API获取更完整信息
        media_id = self._extract_bili_fav_id(url)

        def _extract_via_api():
            """通过B站API获取收藏夹内容（返回完整标题和时长）"""
            if not media_id:
                return None

            # 添加用户cookies
            cookies = {}
            if user_id and user_has_cookies(user_id):
                cookie_path = get_user_cookies_path(user_id)
                try:
                    cookies = parse_netscape_cookie_file(cookie_path)
                except Exception:
                    pass

            return fetch_favorite_entries(media_id, cookies)

        def _extract_via_ytdlp():
            """回退方案：通过 yt-dlp 提取（可能标题不完整）"""
            options = BILI_YDL_OPTIONS.copy()
            options["noplaylist"] = False
            options["extract_flat"] = False  # 不用 flat 模式，获取完整信息
            if user_id and user_has_cookies(user_id):
                options["cookiefile"] = get_user_cookies_path(user_id)

            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    return []
                entries = info.get("entries", [])
                results = []
                for e in entries:
                    if e:
                        title = (
                            e.get("title")
                            or e.get("description", "")[:50]
                            or "未知"
                        )
                        results.append({
                            "title": title,
                            "url": (
                                e.get("webpage_url")
                                or e.get("url", "")
                            ),
                            "duration": e.get("duration", 0),
                        })
                return results

        try:
            # 优先使用B站API（更快且返回完整信息）
            result = await loop.run_in_executor(None, _extract_via_api)
            if result is not None and len(result) > 0:
                return result
            # 回退到 yt-dlp
            print("B站API失败，回退到 yt-dlp 提取")
            return await loop.run_in_executor(None, _extract_via_ytdlp)
        except Exception as e:
            print(f"B站收藏夹提取出错: {e}")
            return []

    @staticmethod
    def _clean_search_query(query: str) -> str:
        """
        清洗用户输入的搜索词，提取有效的歌名和歌手信息。
        例:
          "【AI东雪莲】《大雨还在下》（副业の小曲）"
          → "AI东雪莲 大雨还在下"

          "周杰伦《稻香》官方MV 4K"
          → "周杰伦 稻香"

          "稻香"  (普通搜索词不变)
          → "稻香"
        """
        return clean_search_query(query)

    # ═══════════════════════════════════════
    # 基础播放命令
    # ═══════════════════════════════════════

    async def _play_song(self, ctx: commands.Context, query: str, bili_mode: bool = False):
        """通用播放逻辑，YouTube 和 B站共用"""
        player = self.get_player(ctx.guild.id)
        vc = ctx.voice_client

        channel = ctx.author.voice.channel
        if not vc:
            vc = await channel.connect()
        elif vc.channel != channel:
            await vc.move_to(channel)

        if self._is_bili_url(query):
            bili_mode = True

        # 用户直接输入的搜索词不做清洗，原样传给搜索引擎
        # 清洗只用于歌词搜索（从B站标题自动提取歌名）
        source_label = "B站" if bili_mode else "YouTube / B站"
        is_url = query.strip().startswith(("http://", "https://"))

        async with ctx.typing():
            if is_url:
                await ctx.send(f"🔍 正在从 {source_label} 加载: **{query}**")
            else:
                await ctx.send(
                    f"🔍 正在从 {source_label} 搜索: **{query}**\n"
                    f"💡 *关键词搜索可能不够精准，如需准确匹配请直接粘贴视频链接*"
                )
            info, resolved_bili, resolved_source = (
                await self._search_music_sources(
                    query,
                    user_id=ctx.author.id,
                    prefer_bili=bili_mode,
                )
            )
            if not info:
                return await ctx.send(
                    f"❌ 在 {source_label} 找不到相关音乐，请换个关键词试试。\n"
                    f"💡 建议直接粘贴视频链接，搜索结果更准确"
                )

            song = Song(
                source_url=info.get("url"),
                title=info.get("title", "未知标题"),
                webpage_url=info.get("webpage_url", ""),
                duration=info.get("duration", 0),
                thumbnail=info.get("thumbnail", ""),
                requester=ctx.author,
                is_bili=resolved_bili,
            )

            if not is_url and not bili_mode and resolved_source == "B站":
                await ctx.send("💡 YouTube 未找到结果，已自动切换到 B站音源。")

            if vc.is_playing() or vc.is_paused():
                player.queue.append(song)
                position = len(player.queue)
                embed = song.create_embed(f"已加入队列 #{position} 📋")
                await ctx.send(embed=embed)
            else:
                player.current = song
                player.stream_retries = 0
                self._start_playback(ctx, vc, song, player)
                await ctx.send(embed=song.create_embed())

    @commands.hybrid_command(
        name="播放",
        aliases=["play", "p", "放歌", "来一首", "点歌", "听"],
        help="播放音乐 (关键词自动尝试 YouTube 和 B站)",
    )
    @app_commands.describe(query="搜索关键词或视频链接")
    @_ensure_voice()
    async def play(self, ctx: commands.Context, *, query: str):
        await self._play_song(ctx, query, bili_mode=False)

    @commands.hybrid_command(
        name="b站",
        aliases=["bplay", "bp", "bili", "b站播放", "哔哩哔哩"],
        help="从B站搜索并播放音乐",
    )
    @app_commands.describe(query="B站搜索关键词或视频链接")
    @_ensure_voice()
    async def bplay(self, ctx: commands.Context, *, query: str):
        await self._play_song(ctx, query, bili_mode=True)

    # ═══════════════════════════════════════
    # 歌单导入命令
    # ═══════════════════════════════════════

    @commands.hybrid_command(
        name="网易云",
        aliases=["netease", "网易云歌单", "歌单播放", "wangyiyun"],
        help="播放网易云音乐歌单",
    )
    @app_commands.describe(query="网易云歌单链接或歌单ID")
    @_ensure_voice()
    async def netease(self, ctx: commands.Context, *, query: str):
        playlist_id = self._extract_netease_id(query)
        if not playlist_id:
            return await ctx.send(
                "❌ 请提供有效的网易云歌单链接或ID\n"
                "例: `!网易云 https://music.163.com/playlist?id=123456`\n"
                "例: `!网易云 123456`"
            )

        player = self.get_player(ctx.guild.id)
        vc = ctx.voice_client

        channel = ctx.author.voice.channel
        if not vc:
            vc = await channel.connect()
        elif vc.channel != channel:
            await vc.move_to(channel)

        async with ctx.typing():
            await ctx.send("🔍 正在加载网易云歌单...")
            try:
                name, songs = await self._fetch_netease_playlist(playlist_id)
            except Exception as e:
                return await ctx.send(f"❌ 加载歌单失败: {e}")

            if not songs:
                return await ctx.send("❌ 歌单为空或无法访问（私人歌单无法读取）")

            await ctx.send(
                f"📋 **{name}** — 共 {len(songs)} 首歌，正在加载第一首..."
            )

            # 第一首立即搜索并播放
            first_info, first_is_bili, _ = await self._search_music_sources(
                songs[0]["query"], user_id=ctx.author.id
            )
            if first_info:
                first_song = Song(
                    source_url=first_info.get("url"),
                    title=first_info.get("title", songs[0]["name"]),
                    webpage_url=first_info.get("webpage_url", ""),
                    duration=first_info.get("duration", 0),
                    thumbnail=first_info.get("thumbnail", ""),
                    requester=ctx.author,
                    is_bili=first_is_bili,
                )
                if vc.is_playing() or vc.is_paused():
                    player.queue.append(first_song)
                else:
                    player.current = first_song
                    player.stream_retries = 0
                    self._start_playback(ctx, vc, first_song, player)
                    await ctx.send(embed=first_song.create_embed())
            else:
                await ctx.send(
                    f"⚠️ 第一首 **{songs[0]['name']}** 搜索失败，"
                    "继续加载剩余歌曲..."
                )

            # 剩余歌曲作为懒搜索添加到队列
            for song_info in songs[1:]:
                lazy_song = Song(
                    source_url=None,
                    title=f"{song_info['name']} - {song_info['artist']}",
                    webpage_url="",
                    duration=song_info.get("duration", 0),
                    thumbnail="",
                    requester=ctx.author,
                    search_query=song_info["query"],
                )
                player.queue.append(lazy_song)

            await ctx.send(
                f"✅ 已将剩余 **{len(songs) - 1}** 首歌添加到队列"
                "（播放时自动搜索）"
            )

    @commands.hybrid_command(
        name="收藏",
        aliases=["b站收藏", "收藏夹", "fav", "b站收藏夹"],
        help="播放B站收藏夹/播放列表",
    )
    @app_commands.describe(url="B站收藏夹链接")
    @_ensure_voice()
    async def bili_fav(self, ctx: commands.Context, *, url: str):
        user_id = ctx.author.id
        if not user_has_cookies(user_id):
            return await ctx.send(
                "❌ 你还没有绑定B站账号\n"
                "请先用 `!绑定b站` 命令上传你的 cookies.txt 文件"
            )

        player = self.get_player(ctx.guild.id)
        vc = ctx.voice_client

        channel = ctx.author.voice.channel
        if not vc:
            vc = await channel.connect()
        elif vc.channel != channel:
            await vc.move_to(channel)

        async with ctx.typing():
            await ctx.send("🔍 正在加载B站收藏夹...")
            entries = await self._extract_bili_playlist(url, user_id=user_id)

            if not entries:
                return await ctx.send(
                    "❌ 收藏夹为空或无法访问，请检查链接和 Cookies 是否正确\n"
                    "Cookies 可能已过期，试试重新 `!绑定b站` 上传"
                )

            await ctx.send(
                f"📋 共找到 **{len(entries)}** 个视频，正在加载第一首..."
            )

            # 第一首立即搜索并播放
            first_url = entries[0].get("url", "")
            first_info = await self._search(
                first_url, bili_mode=True, user_id=user_id
            )
            if first_info:
                first_song = Song(
                    source_url=first_info.get("url"),
                    title=first_info.get(
                        "title", entries[0].get("title", "未知")
                    ),
                    webpage_url=first_info.get("webpage_url", ""),
                    duration=first_info.get("duration", 0),
                    thumbnail=first_info.get("thumbnail", ""),
                    requester=ctx.author,
                    is_bili=True,
                )
                if vc.is_playing() or vc.is_paused():
                    player.queue.append(first_song)
                else:
                    player.current = first_song
                    player.stream_retries = 0
                    self._start_playback(ctx, vc, first_song, player)
                    await ctx.send(embed=first_song.create_embed())
            else:
                await ctx.send("⚠️ 第一个视频搜索失败，继续加载剩余...")

            # 剩余视频作为懒搜索添加到队列
            for entry in entries[1:]:
                lazy_song = Song(
                    source_url=None,
                    title=entry.get("title", "未知"),
                    webpage_url=entry.get("url", ""),
                    duration=entry.get("duration", 0),
                    thumbnail="",
                    requester=ctx.author,
                    is_bili=True,
                    search_query=entry.get("url", ""),
                )
                player.queue.append(lazy_song)

            await ctx.send(
                f"✅ 已将剩余 **{len(entries) - 1}** 个视频添加到队列"
                "（播放时自动搜索）"
            )

    @commands.hybrid_command(
        name="合集",
        aliases=["b站合集", "系列", "collection", "up合集"],
        help="播放B站UP主的合集/系列",
    )
    @app_commands.describe(url="B站合集或系列链接")
    @_ensure_voice()
    async def bili_collection(self, ctx: commands.Context, *, url: str):
        player = self.get_player(ctx.guild.id)
        vc = ctx.voice_client

        channel = ctx.author.voice.channel
        if not vc:
            vc = await channel.connect()
        elif vc.channel != channel:
            await vc.move_to(channel)

        # 检查是否是合集链接
        if not self._extract_bili_collection_info(url):
            return await ctx.send(
                "❌ 请提供有效的B站合集或系列链接\n"
                "例: `！合集 https://space.bilibili.com/xxx/channel/"
                "collectiondetail?sid=xxx`\n"
                "例: `！合集 https://space.bilibili.com/xxx/channel/"
                "seriesdetail?sid=xxx`"
            )

        user_id = ctx.author.id
        async with ctx.typing():
            if not user_has_cookies(user_id):
                await ctx.send(
                    "ℹ️ 你还没有绑定 B站 cookies。合集可以尝试加载，"
                    "但如果遇到 412/风控，请用 `！绑定b站` 上传 cookies.txt。"
                )
            await ctx.send("🔍 正在加载B站合集...")
            name, entries = await self._fetch_bili_collection(
                url, user_id=user_id
            )

            if not entries:
                return await ctx.send(
                    "❌ 合集为空或无法访问，请检查链接是否正确"
                )

            await ctx.send(
                f"📋 **{name}** — 共 {len(entries)} 个视频，"
                "正在加载第一首..."
            )

            # 第一首立即搜索并播放
            first_url = entries[0].get("url", "")
            first_info = await self._search(
                first_url, bili_mode=True, user_id=user_id
            )
            if first_info:
                first_song = Song(
                    source_url=first_info.get("url"),
                    title=first_info.get(
                        "title", entries[0].get("title", "未知")
                    ),
                    webpage_url=first_info.get("webpage_url", ""),
                    duration=first_info.get("duration", 0),
                    thumbnail=first_info.get("thumbnail", ""),
                    requester=ctx.author,
                    is_bili=True,
                )
                if vc.is_playing() or vc.is_paused():
                    player.queue.append(first_song)
                else:
                    player.current = first_song
                    player.stream_retries = 0
                    self._start_playback(ctx, vc, first_song, player)
                    await ctx.send(embed=first_song.create_embed())
            else:
                await ctx.send("⚠️ 第一个视频搜索失败，继续加载剩余...")

            # 剩余视频作为懒搜索添加到队列
            for entry in entries[1:]:
                lazy_song = Song(
                    source_url=None,
                    title=entry.get("title", "未知"),
                    webpage_url=entry.get("url", ""),
                    duration=entry.get("duration", 0),
                    thumbnail="",
                    requester=ctx.author,
                    is_bili=True,
                    search_query=entry.get("url", ""),
                )
                player.queue.append(lazy_song)

            await ctx.send(
                f"✅ 已将剩余 **{len(entries) - 1}** 个视频添加到队列"
                "（播放时自动搜索）"
            )

    @commands.command(
        name="绑定b站",
        aliases=["绑定B站", "绑定bili", "绑定bilibili", "上传cookies"],
        help="上传你的B站 cookies.txt 绑定账号（私聊也可以）",
    )
    async def bind_bili(self, ctx: commands.Context):
        # 检查是否有附件
        if ctx.message.attachments:
            attachment = ctx.message.attachments[0]
            if not attachment.filename.endswith(".txt"):
                return await ctx.send("❌ 请上传 `.txt` 格式的 cookies 文件")
            if attachment.size > 1_000_000:  # 1MB
                return await ctx.send("❌ 文件太大，cookies.txt 通常不到 100KB")

            # 下载并保存到 cookies/<user_id>.txt
            cookies_path = get_user_cookies_path(ctx.author.id)
            content = await attachment.read()
            try:
                text = content.decode("utf-8")
                validate_bili_cookie_text(text)
            except UnicodeDecodeError:
                return await ctx.send("❌ cookies 文件必须是 UTF-8 文本")
            except ValueError as exc:
                return await ctx.send(f"❌ cookies 文件无效: {exc}")

            replaced = replace_cookie_file(cookies_path, content)
            action = "已删除旧 cookies 并更新" if replaced else "已保存"

            await ctx.send(
                f"✅ **{ctx.author.display_name}** 的B站账号{action}成功！\n"
                "现在你可以用 `!收藏 <收藏夹链接>` 播放你的收藏夹了"
            )
            # 如果是在服务器公开频道发的，提醒删除消息
            if ctx.guild:
                await ctx.send(
                    "⚠️ 建议删除你刚才发的消息（包含 cookies 文件），"
                    "或者下次通过**私聊**发送更安全"
                )
        else:
            # 没有附件，显示教程
            embed = discord.Embed(
                title="🔗 绑定B站账号",
                description=(
                    "每个人可以绑定自己的B站账号，"
                    "绑定后可以用 `!收藏` 播放自己的收藏夹"
                ),
                color=discord.Color.orange(),
            )
            embed.add_field(
                name="步骤 1: 安装浏览器扩展",
                value=(
                    "Chrome: 安装 [Get cookies.txt LOCALLY]"
                    "(https://chromewebstore.google.com/detail/"
                    "get-cookiestxt-locally/"
                    "cclelndahbckbenkjhflpdbgdldlbecc)"
                ),
                inline=False,
            )
            embed.add_field(
                name="步骤 2: 导出 Cookies",
                value=(
                    "1. 打开 [bilibili.com](https://www.bilibili.com/) "
                    "并确保已登录\n"
                    "2. 点击扩展图标，选择 **导出** 为 `cookies.txt`"
                ),
                inline=False,
            )
            embed.add_field(
                name="步骤 3: 上传文件",
                value=(
                    "在这里（或私聊机器人）发送:\n"
                    "`!绑定b站` 并**附带 cookies.txt 文件**\n\n"
                    "💡 **建议通过私聊发送**，更安全"
                ),
                inline=False,
            )
            # 显示当前用户的绑定状态
            if user_has_cookies(ctx.author.id):
                embed.set_footer(text="✅ 你已绑定B站账号")
            else:
                embed.set_footer(text="❌ 你还未绑定B站账号")
            await ctx.send(embed=embed)

    @commands.command(
        name="解绑b站",
        aliases=["解绑B站", "解绑bili", "删除cookies"],
        help="解绑你的B站账号（删除已保存的 cookies）",
    )
    async def unbind_bili(self, ctx: commands.Context):
        cookies_path = get_user_cookies_path(ctx.author.id)
        if os.path.exists(cookies_path):
            os.remove(cookies_path)
            await ctx.send(f"✅ **{ctx.author.display_name}** 的B站账号已解绑")
        else:
            await ctx.send("❌ 你还没有绑定B站账号")

    @commands.command(
        name="设置cookies",
        aliases=["cookie设置", "cookies", "cookie教程"],
        help="查看Cookies设置教程（同 !绑定b站）",
    )
    async def setup_cookies(self, ctx: commands.Context):
        await self.bind_bili(ctx)

    # ═══════════════════════════════════════
    # 播放控制命令
    # ═══════════════════════════════════════

    @commands.hybrid_command(
        name="暂停", aliases=["pause", "等一下", "停一下"], help="暂停播放"
    )
    @_ensure_voice()
    async def pause(self, ctx: commands.Context):
        vc = ctx.voice_client
        if vc and vc.is_playing():
            vc.pause()
            await ctx.send("⏸️ 已暂停播放。")
        else:
            await ctx.send("❌ 当前没有正在播放的音乐。")

    @commands.hybrid_command(
        name="继续", aliases=["resume", "继续播放", "接着放"], help="恢复播放"
    )
    @_ensure_voice()
    async def resume(self, ctx: commands.Context):
        vc = ctx.voice_client
        if vc and vc.is_paused():
            vc.resume()
            await ctx.send("▶️ 已恢复播放。")
        else:
            await ctx.send("❌ 当前没有暂停的音乐。")

    @commands.hybrid_command(
        name="下一首",
        aliases=["skip", "s", "跳过", "切歌", "换一首"],
        help="跳过当前曲目",
    )
    @_ensure_voice()
    async def skip(self, ctx: commands.Context):
        vc = ctx.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            player = self.get_player(ctx.guild.id)
            player.loop = False
            self.skip_votes.pop(ctx.guild.id, None)
            player.intentional_stop = True
            vc.stop()
            await ctx.send("⏭️ 已跳过当前曲目。")
        else:
            await ctx.send("❌ 当前没有正在播放的音乐。")

    @commands.hybrid_command(
        name="投票跳过",
        aliases=["voteskip", "vskip", "投票切歌"],
        help="发起或参与投票跳过当前曲目",
    )
    @_ensure_voice()
    async def vote_skip(self, ctx: commands.Context):
        vc = ctx.voice_client
        player = self.get_player(ctx.guild.id)
        if not vc or not (vc.is_playing() or vc.is_paused()) or not player.current:
            return await ctx.send("❌ 当前没有正在播放的音乐。")

        channel = ctx.author.voice.channel
        listeners = [
            member for member in channel.members
            if not member.bot
        ]
        required = 1 if len(listeners) <= 1 else max(2, math.ceil(len(listeners) / 2))
        votes = self.skip_votes.setdefault(ctx.guild.id, set())
        if ctx.author.id in votes:
            return await ctx.send(
                f"🗳️ 你已经投过票了。当前 **{len(votes)}/{required}**"
            )

        votes.add(ctx.author.id)
        if len(votes) >= required:
            player.loop = False
            self.skip_votes.pop(ctx.guild.id, None)
            player.intentional_stop = True
            vc.stop()
            return await ctx.send(
                f"⏭️ 投票通过，已跳过当前曲目。(**{len(votes)}/{required}**)"
            )

        await ctx.send(f"🗳️ 已投票跳过。当前 **{len(votes)}/{required}**")

    @commands.hybrid_command(
        name="停止",
        aliases=["stop", "leave", "断开", "退出", "走吧", "拜拜"],
        help="停止播放并离开频道",
    )
    @_ensure_voice()
    async def stop(self, ctx: commands.Context):
        vc = ctx.voice_client
        if vc:
            player = self.get_player(ctx.guild.id)
            player.clear()
            self.skip_votes.pop(ctx.guild.id, None)
            await vc.disconnect()
            await ctx.send("⏹️ 已停止播放并离开语音频道。")
        else:
            await ctx.send("❌ 机器人不在语音频道中。")

    # ═══════════════════════════════════════
    # 队列管理命令
    # ═══════════════════════════════════════

    @commands.hybrid_command(
        name="队列",
        aliases=["queue", "q", "列表", "播放列表"],
        help="查看播放队列",
    )
    async def queue(self, ctx: commands.Context):
        player = self.get_player(ctx.guild.id)

        if not player.current and not player.queue:
            return await ctx.send("📭 播放队列为空。")

        embed = discord.Embed(title="📋 播放队列", color=discord.Color.green())

        if player.current:
            loop_icon = " 🔂" if player.loop else ""
            current_text = (
                f"[{player.current.title}]({player.current.webpage_url})"
                if player.current.webpage_url
                else player.current.title
            )
            embed.add_field(
                name=f"正在播放{loop_icon}",
                value=f"{current_text} — `{player.current.duration_str}`",
                inline=False,
            )

        if player.queue:
            queue_list = []
            for i, song in enumerate(list(player.queue)[:10], 1):
                pending = " ⏳" if not song.is_resolved else ""
                song_text = (
                    f"[{song.title}]({song.webpage_url})"
                    if song.webpage_url
                    else song.title
                )
                queue_list.append(
                    f"`{i}.` {song_text} — `{song.duration_str}`{pending}"
                )
            if len(player.queue) > 10:
                queue_list.append(
                    f"\n... 还有 **{len(player.queue) - 10}** 首"
                )
            embed.add_field(
                name="等待播放",
                value="\n".join(queue_list),
                inline=False,
            )

        status = []
        if player.loop:
            status.append("🔂 单曲循环")
        if player.loop_queue:
            status.append("🔁 列表循环")
        status_text = " | ".join(status) if status else "正常播放"
        embed.set_footer(
            text=(
                f"共 {len(player.queue)} 首等待 | "
                f"音量: {int(player.volume * 100)}% | {status_text}"
            )
        )

        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="在听什么",
        aliases=["nowplaying", "np", "当前", "这首是什么", "在放什么"],
        help="查看当前播放的曲目",
    )
    async def nowplaying(self, ctx: commands.Context):
        player = self.get_player(ctx.guild.id)
        if player.current:
            await ctx.send(embed=player.current.create_embed())
        else:
            await ctx.send("❌ 当前没有正在播放的音乐。")

    @commands.hybrid_command(
        name="音量",
        aliases=["volume", "vol", "声音"],
        help="设置音量 (0-100)",
    )
    @app_commands.describe(vol="音量大小 0-100")
    @_ensure_voice()
    async def volume(self, ctx: commands.Context, vol: int):
        if not 0 <= vol <= 100:
            return await ctx.send("❌ 音量范围: 0-100")

        player = self.get_player(ctx.guild.id)
        player.volume = vol / 100.0

        vc = ctx.voice_client
        if vc and vc.source:
            vc.source.volume = player.volume

        await ctx.send(f"🔊 音量已设置为 **{vol}%**")

    @commands.hybrid_command(
        name="单曲循环", aliases=["loop", "循环", "重复"], help="切换单曲循环"
    )
    async def loop(self, ctx: commands.Context):
        player = self.get_player(ctx.guild.id)
        player.loop = not player.loop
        if player.loop:
            player.loop_queue = False
        status = "开启 🔂" if player.loop else "关闭"
        await ctx.send(f"🔂 单曲循环: **{status}**")

    @commands.hybrid_command(
        name="列表循环",
        aliases=["loopqueue", "lq", "全部循环", "循环列表"],
        help="切换列表循环",
    )
    async def loopqueue(self, ctx: commands.Context):
        player = self.get_player(ctx.guild.id)
        player.loop_queue = not player.loop_queue
        if player.loop_queue:
            player.loop = False
        status = "开启 🔁" if player.loop_queue else "关闭"
        await ctx.send(f"🔁 列表循环: **{status}**")

    @commands.hybrid_command(
        name="移除",
        aliases=["remove", "rm", "删掉", "删除"],
        help="移除队列中指定位置的曲目",
    )
    @app_commands.describe(index="要移除的队列位置")
    async def remove(self, ctx: commands.Context, index: int):
        player = self.get_player(ctx.guild.id)
        if not 1 <= index <= len(player.queue):
            return await ctx.send(
                f"❌ 无效的位置，队列共有 {len(player.queue)} 首。"
            )
        queue_list = list(player.queue)
        removed = queue_list.pop(index - 1)
        player.queue = deque(queue_list)
        await ctx.send(f"🗑️ 已移除: **{removed.title}**")

    @commands.hybrid_command(
        name="清空", aliases=["clear", "全部删除", "清除"], help="清空播放队列"
    )
    async def clear(self, ctx: commands.Context):
        player = self.get_player(ctx.guild.id)
        player.queue.clear()
        await ctx.send("🗑️ 播放队列已清空。")

    @commands.hybrid_command(
        name="导出队列",
        aliases=["exportqueue", "队列导出"],
        help="导出队列；提供名称时保存到本地队列库",
    )
    @app_commands.describe(name="可选: 保存到本地队列库的名称")
    async def export_queue(self, ctx: commands.Context, *, name: str = ""):
        player = self.get_player(ctx.guild.id)
        if not player.current and not player.queue:
            return await ctx.send("📭 播放队列为空，没什么可导出的。")

        payload = build_snapshot(player)
        if name:
            try:
                path = save_named_queue(ctx.guild.id, name, payload)
            except Exception as exc:
                return await ctx.send(f"❌ 保存失败: {exc}")
            return await ctx.send(
                f"💾 已将当前队列保存为歌单 **{path.stem}**。\n"
                f"之后可用 `！播放歌单 {path.stem}` 播放。"
            )

        raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        file = discord.File(
            io.BytesIO(raw),
            filename=f"music-queue-{ctx.guild.id}.json",
        )
        await ctx.send("📦 已导出当前队列。", file=file)

    @commands.hybrid_command(
        name="创建歌单",
        aliases=["createplaylist", "新建歌单"],
        help="通过对话逐首创建一个本地歌单",
    )
    @app_commands.describe(name="可选：直接指定歌单名称")
    async def create_playlist(
        self, ctx: commands.Context, *, name: str = ""
    ):
        session_key = (ctx.guild.id, ctx.author.id)
        if session_key in self.playlist_sessions:
            return await ctx.send("❌ 你已经在创建歌单了，请先完成当前歌单。")

        def check(message: discord.Message) -> bool:
            return (
                message.author.id == ctx.author.id
                and message.channel.id == ctx.channel.id
                and not message.author.bot
            )

        async def wait_for_input() -> str | None:
            try:
                message = await self.bot.wait_for(
                    "message", check=check, timeout=600
                )
            except asyncio.TimeoutError:
                await ctx.send("⌛ 创建歌单已超时，本次内容没有保存。")
                return None
            return message.content.strip()

        self.playlist_sessions.add(session_key)
        try:
            while True:
                if not name.strip():
                    await ctx.send(
                        "📝 请输入想要创建的歌单名字。\n"
                        "输入 `取消创建` 可随时退出。"
                    )
                    name = await wait_for_input()
                    if name is None:
                        return
                if name in {"取消", "取消创建"}:
                    return await ctx.send("已取消创建歌单。")
                try:
                    safe_name = sanitize_queue_name(name)
                except ValueError as exc:
                    await ctx.send(f"❌ {exc}，请重新输入歌单名字。")
                    name = ""
                    continue
                if safe_name in list_named_queues(ctx.guild.id):
                    await ctx.send(f"❌ 歌单 **{safe_name}** 已存在。")
                    await ctx.send("请换一个歌单名字。")
                    name = ""
                    continue
                break

            await ctx.send(
                f"🎵 正在创建歌单 **{safe_name}**。\n"
                "请每次发送一首歌的名称或链接，我会使用播放器的默认搜索源添加。\n"
                "全部输入完毕后发送 `完成歌单`；放弃请发送 `取消创建`。"
            )

            records: list[dict] = []
            while True:
                query = await wait_for_input()
                if query is None:
                    return
                if query in {"取消", "取消创建"}:
                    return await ctx.send("已取消创建歌单，本次内容没有保存。")
                if query in {"完成", "完成歌单", "结束", "结束歌单"}:
                    if not records:
                        await ctx.send(
                            "❌ 歌单里还没有歌曲。请先输入歌曲，"
                            "或发送 `取消创建`。"
                        )
                        continue
                    payload = empty_snapshot()
                    payload["queue"] = records
                    path = save_named_queue(ctx.guild.id, safe_name, payload)
                    return await ctx.send(
                        f"✅ 歌单 **{path.stem}** 创建完成，共 **{len(records)}** 首。\n"
                        f"输入 `！播放歌单 {path.stem}` 即可播放并自动显示歌词。"
                    )

                await ctx.send(f"🔍 正在查找: **{query}**")
                record = await self._resolve_playlist_record(query, ctx.author.id)
                if not record:
                    await ctx.send(
                        "⚠️ 没有找到这首歌，未加入歌单。"
                        "请重新输入，或发送 `完成歌单`。"
                    )
                    continue
                records.append(record)
                await ctx.send(
                    f"➕ 已添加 **{record['title']}** "
                    f"（当前 {len(records)} 首）。\n"
                    "继续输入下一首，完成时发送 `完成歌单`。"
                )
        finally:
            self.playlist_sessions.discard(session_key)

    @commands.hybrid_command(
        name="歌单添加",
        aliases=["playlistadd", "添加到歌单"],
        help="向命名歌单添加当前歌曲或指定歌曲",
    )
    @app_commands.describe(
        name="歌单名称",
        query="歌曲关键词或链接；留空时添加当前歌曲",
    )
    async def add_to_playlist(
        self, ctx: commands.Context, name: str, *, query: str = ""
    ):
        try:
            load_named_queue(ctx.guild.id, name)
        except Exception as exc:
            return await ctx.send(f"❌ 读取歌单失败: {exc}")

        if query:
            await ctx.send(f"🔍 正在查找要加入歌单的歌曲: **{query}**")
            record = await self._resolve_playlist_record(query, ctx.author.id)
            if not record:
                return await ctx.send("❌ 没有找到这首歌，未修改歌单。")
        else:
            player = self.get_player(ctx.guild.id)
            if not player.current:
                return await ctx.send(
                    "❌ 当前没有播放歌曲，请提供歌名或链接。\n"
                    "例: `！歌单添加 通勤 稻香`"
                )
            record = song_to_record(player.current)
            record["source_url"] = None
            record["search_query"] = (
                record.get("search_query")
                or record.get("webpage_url")
                or record["title"]
            )

        try:
            path, total = append_named_queue_record(ctx.guild.id, name, record)
        except Exception as exc:
            return await ctx.send(f"❌ 添加失败: {exc}")
        await ctx.send(
            f"➕ 已将 **{record['title']}** 添加到 **{path.stem}** "
            f"（共 {total} 首）。"
        )

    @commands.hybrid_command(
        name="保存歌单",
        aliases=["savequeue", "存队列", "保存队列"],
        help="把当前播放队列保存为本地歌单",
    )
    @app_commands.describe(name="歌单名称")
    async def save_queue(self, ctx: commands.Context, *, name: str):
        try:
            safe_name = await self._save_current_queue(ctx, name)
        except Exception as exc:
            return await ctx.send(f"❌ 保存失败: {exc}")
        if safe_name:
            await ctx.send(
                f"💾 已将当前队列保存为歌单 **{safe_name}**。\n"
                f"之后可用 `！播放歌单 {safe_name}` 播放。"
            )

    @commands.hybrid_command(
        name="查看歌单",
        aliases=[
            "playlistinfo",
            "歌单内容",
            "歌单详情",
            "歌单",
            "歌单列表",
            "队列库",
            "队列列表",
            "本地队列",
        ],
        help="查看本服务器的歌单名称或指定歌单内容",
    )
    @app_commands.describe(name="可选：要查看的歌单名称")
    async def view_playlist(
        self, ctx: commands.Context, *, name: str = ""
    ):
        if not name.strip():
            names = list_named_queues(ctx.guild.id)
            if not names:
                return await ctx.send(
                    "📭 本服务器还没有歌单。输入 `！创建歌单` 开始创建。"
                )
            lines = []
            for index, playlist_name in enumerate(names, 1):
                try:
                    payload = load_named_queue(ctx.guild.id, playlist_name)
                    count = len(records_from_snapshot(payload, include_current=True))
                except Exception:
                    count = 0
                lines.append(f"`{index}.` **{playlist_name}** · {count} 首")
            embed = discord.Embed(
                title="本地歌单",
                description="\n".join(lines),
                color=discord.Color.green(),
            )
            embed.set_footer(text="输入 ！查看歌单 <名称> 查看歌曲内容")
            return await ctx.send(embed=embed)

        try:
            safe_name = sanitize_queue_name(name)
            payload = load_named_queue(ctx.guild.id, safe_name)
            records = records_from_snapshot(payload, include_current=True)
        except Exception as exc:
            return await ctx.send(f"❌ 查看歌单失败: {exc}")

        view = PlaylistPager(safe_name, records, ctx.author.id)
        view.message = await ctx.send(embed=view.create_embed(), view=view)

    @commands.hybrid_command(
        name="播放歌单",
        aliases=["playqueue", "读取队列", "播放队列"],
        help="读取本地歌单并加入当前播放队列",
    )
    @app_commands.describe(name="歌单名称")
    @_ensure_voice()
    async def play_saved_queue(self, ctx: commands.Context, *, name: str):
        try:
            payload = load_named_queue(ctx.guild.id, name)
            records = records_from_snapshot(payload, include_current=True)
        except Exception as exc:
            return await ctx.send(f"❌ 读取失败: {exc}")

        if not records:
            return await ctx.send("📭 这个歌单是空的。")

        player = self.get_player(ctx.guild.id)
        vc = ctx.voice_client
        channel = ctx.author.voice.channel
        if not vc:
            vc = await channel.connect()
        elif vc.channel != channel:
            await vc.move_to(channel)

        added = self._append_records_to_queue(
            player, records, ctx.author, force_resolve=True
        )
        player.auto_lyrics = True
        safe_name = sanitize_queue_name(name)
        await ctx.send(
            f"📂 已读取 **{safe_name}**，加入 **{added}** 首歌。\n"
            "🎤 已开启自动歌词；每首歌开始播放时会显示歌词。"
        )

        if vc and not vc.is_playing() and not vc.is_paused():
            await self._async_play_next(ctx)

    @commands.hybrid_command(
        name="删除歌单",
        aliases=["deletequeue", "删队列", "删除队列"],
        help="删除本地保存的命名歌单",
    )
    @app_commands.describe(name="歌单名称")
    async def delete_saved_queue(self, ctx: commands.Context, *, name: str):
        try:
            safe_name = delete_named_queue(ctx.guild.id, name)
        except Exception as exc:
            return await ctx.send(f"❌ 删除失败: {exc}")
        await ctx.send(f"🗑️ 已删除歌单 **{safe_name}**。")

    @commands.command(
        name="导入队列",
        aliases=["importqueue", "队列导入", "恢复队列"],
        help="从 JSON 附件导入等待队列；提供名称时保存到本地队列库",
    )
    async def import_queue(self, ctx: commands.Context, *, name: str = ""):
        try:
            payload = await self._read_queue_attachment(ctx)
            records = validate_snapshot(payload)
        except Exception as exc:
            return await ctx.send(f"❌ 导入失败: {exc}")

        if name:
            try:
                path = save_named_queue(ctx.guild.id, name, payload)
            except Exception as exc:
                return await ctx.send(f"❌ 保存失败: {exc}")
            return await ctx.send(
                f"💾 已上传并保存为 **{path.stem}**。\n"
                f"之后可用 `！播放歌单 {path.stem}` 播放。"
            )

        player = self.get_player(ctx.guild.id)
        self._append_records_to_queue(player, records, ctx.author)

        await ctx.send(f"✅ 已导入 **{len(records)}** 首歌到队列末尾。")

    @commands.command(
        name="上传队列",
        aliases=["uploadqueue", "上传歌单"],
        help="上传 JSON 附件并保存到本地队列库",
    )
    async def upload_queue(self, ctx: commands.Context, *, name: str):
        try:
            payload = await self._read_queue_attachment(ctx)
            path = save_named_queue(ctx.guild.id, name, payload)
        except Exception as exc:
            return await ctx.send(f"❌ 上传失败: {exc}")
        await ctx.send(
            f"💾 已上传并保存为 **{path.stem}**。\n"
            f"之后可用 `！播放歌单 {path.stem}` 播放。"
        )

    @commands.hybrid_command(
        name="随机",
        aliases=["shuffle", "打乱", "随机播放"],
        help="随机打乱队列顺序",
    )
    async def shuffle(self, ctx: commands.Context):
        import random

        player = self.get_player(ctx.guild.id)
        if len(player.queue) < 2:
            return await ctx.send("❌ 队列中至少需要 2 首歌才能打乱。")
        queue_list = list(player.queue)
        random.shuffle(queue_list)
        player.queue = deque(queue_list)
        await ctx.send(f"🔀 已打乱队列中的 **{len(player.queue)}** 首歌。")

    @commands.hybrid_command(
        name="跳转",
        aliases=["skipto", "跳到", "跳转到"],
        help="跳转到队列中指定位置",
    )
    @app_commands.describe(index="要跳转到的队列位置")
    @_ensure_voice()
    async def skipto(self, ctx: commands.Context, index: int):
        player = self.get_player(ctx.guild.id)
        if not 1 <= index <= len(player.queue):
            return await ctx.send(
                f"❌ 无效的位置，队列共有 {len(player.queue)} 首。"
            )
        for _ in range(index - 1):
            player.queue.popleft()
        player.loop = False
        vc = ctx.voice_client
        if vc:
            self.skip_votes.pop(ctx.guild.id, None)
            player.intentional_stop = True
            vc.stop()
        await ctx.send(f"⏭️ 已跳转到队列第 **{index}** 首。")


    # ═══════════════════════════════════════
    # 音效滤镜命令
    # ═══════════════════════════════════════

    async def _apply_filter(
        self, ctx: commands.Context, filter_name: str | None
    ):
        """通用滤镜应用逻辑"""
        player = self.get_player(ctx.guild.id)
        vc = ctx.voice_client

        if not vc or not (vc.is_playing() or vc.is_paused()):
            return await ctx.send("❌ 当前没有正在播放的音乐。")

        if not player.current or not player.current.is_resolved:
            return await ctx.send("❌ 当前歌曲无法应用滤镜。")

        old_filter = player.audio_filter
        player.audio_filter = filter_name
        player.replay_current = True
        player.intentional_stop = True
        vc.stop()  # 触发 _play_next → replay_current

        label = filter_name or "原声"
        old_label = old_filter or "原声"
        await ctx.send(f"🎛️ 音效: **{old_label}** → **{label}**")

    @commands.hybrid_command(
        name="滤镜",
        aliases=["filter", "音效", "效果"],
        help="切换音效滤镜 (低音炮/夜核/慢放/加速/8D/回声/空灵/关闭)",
    )
    @app_commands.describe(name="滤镜名称: 低音炮/夜核/慢放/加速/8D/回声/空灵/关闭")
    @_ensure_voice()
    async def audio_filter(self, ctx: commands.Context, *, name: str):
        name = name.strip()
        if name in ("关闭", "取消", "原声", "off", "none", "关"):
            await self._apply_filter(ctx, None)
        elif name in AUDIO_FILTERS:
            await self._apply_filter(ctx, name)
        else:
            available = " / ".join(AUDIO_FILTERS.keys())
            await ctx.send(
                f"❌ 未知滤镜: **{name}**\n"
                f"可用: `{available}` / `关闭`"
            )

    @commands.hybrid_command(
        name="滤镜列表",
        aliases=["filters", "音效列表", "效果列表"],
        help="查看可用音效滤镜",
    )
    async def audio_filters(self, ctx: commands.Context):
        available = " / ".join(AUDIO_FILTERS.keys())
        await ctx.send(f"🎛️ 可用滤镜: `{available}` / `关闭`")

    @commands.hybrid_command(
        name="低音炮", aliases=["bass", "bassboost"], help="开启低音炮效果"
    )
    @_ensure_voice()
    async def bass(self, ctx: commands.Context):
        await self._apply_filter(ctx, "低音炮")

    @commands.hybrid_command(
        name="夜核", aliases=["nightcore", "nc"], help="开启夜核效果（加速+升调）"
    )
    @_ensure_voice()
    async def nightcore(self, ctx: commands.Context):
        await self._apply_filter(ctx, "夜核")

    @commands.hybrid_command(
        name="取消滤镜",
        aliases=["nofilter", "原声", "关闭滤镜"],
        help="关闭所有音效滤镜",
    )
    @_ensure_voice()
    async def no_filter(self, ctx: commands.Context):
        await self._apply_filter(ctx, None)

    # ═══════════════════════════════════════
    # 歌词显示 (QQ Music + LRCLIB 回退)
    # ═══════════════════════════════════════

    @staticmethod
    async def _fetch_qq_lyrics(
        keyword: str,
    ) -> tuple[str, str, str, str] | None:
        """
        通过 QQ Music 搜索歌曲并获取歌词。
        QQ Music 搜索更精准（第一个结果通常就是原唱），歌词库也更全。
        返回 (歌名, 歌手, 歌词文本, 来源) 或 None
        """
        loop = asyncio.get_event_loop()

        def _search_and_get():
            import json as _json

            # ── Step 1: QQ Music 搜索歌曲 ──
            query_data = _json.dumps({
                "search": {
                    "method": "DoSearchForQQMusicDesktop",
                    "module": "music.search.SearchCgiService",
                    "param": {
                        "search_type": 0,
                        "query": keyword,
                        "page_num": 1,
                        "num_per_page": 10,
                    },
                }
            })
            try:
                search_data = request_json(
                    "GET",
                    "https://u.y.qq.com/cgi-bin/musicu.fcg",
                    params={"data": query_data},
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=10,
                )
                song_list = (
                    search_data.get("search", {})
                    .get("data", {})
                    .get("body", {})
                    .get("song", {})
                    .get("list", [])
                )
            except Exception:
                return None

            if not song_list:
                return None

            # ── Step 2: 相关性过滤 + 排序 ──
            import unicodedata

            def _normalize(text: str) -> str:
                text = text.lower()
                text = unicodedata.normalize("NFKC", text)
                return re.sub(
                    r"[^\w\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]",
                    "", text,
                )

            kw_n = _normalize(keyword)
            skip_tags = [
                "伴奏", "cover", "翻唱", "钢琴版", "女声版",
                "童声", "live", "柔情版", "remix", "改编",
                "鬼畜", "纯音乐", "instrumental",
            ]

            def _is_relevant(name_n: str) -> bool:
                """歌名与关键词是否相关"""
                if not name_n or not kw_n:
                    return False
                if name_n == kw_n or name_n in kw_n or kw_n in name_n:
                    return True
                for part in keyword.lower().replace("-", " ").split():
                    pn = _normalize(part)
                    if pn and (pn == name_n or pn in name_n or name_n in pn):
                        return True
                # 中文字符重叠 ≥50%
                kw_cn = set(c for c in kw_n if "\u4e00" <= c <= "\u9fff")
                nm_cn = set(c for c in name_n if "\u4e00" <= c <= "\u9fff")
                if kw_cn and nm_cn:
                    overlap = len(kw_cn & nm_cn)
                    if overlap >= min(len(kw_cn), len(nm_cn)) * 0.5:
                        return True
                return False

            # 过滤并排序: 相关 + 非翻唱 优先
            candidates = []
            for s in song_list:
                name = s.get("name", "")
                name_n = _normalize(name)
                name_lower = name.lower()

                if not _is_relevant(name_n):
                    continue

                # 标签惩罚
                penalty = 0
                if any(tag in name_lower for tag in skip_tags):
                    penalty += 100
                singers = s.get("singer", [])
                artist_str = " ".join(
                    a.get("name", "").lower() for a in singers
                )
                ai_tags = ["ai", "翻唱", "cover", "洛天依", "初音"]
                if any(tag in artist_str for tag in ai_tags):
                    penalty += 80
                # 歌名完全匹配加分
                if name_n == kw_n:
                    penalty -= 50

                candidates.append((penalty, s))

            candidates.sort(key=lambda x: x[0])

            if not candidates:
                return None

            # ── Step 3: 依次获取歌词 ──
            for _, song in candidates:
                song_mid = song.get("mid", "")
                if not song_mid:
                    continue

                song_name = song.get("name", "")
                singers = song.get("singer", [])
                artist_display = " / ".join(
                    a.get("name", "") for a in singers
                )

                try:
                    lyric_data = request_json(
                        "GET",
                        "https://c.y.qq.com/lyric/fcgi-bin/"
                        "fcg_query_lyric_new.fcg",
                        params={
                            "songmid": song_mid,
                            "format": "json",
                            "nobase64": 1,
                        },
                        headers={
                            "User-Agent": "Mozilla/5.0",
                            "Referer": "https://y.qq.com/",
                        },
                        timeout=10,
                    )
                    raw_lrc = lyric_data.get("lyric", "")
                except Exception:
                    continue

                if not raw_lrc:
                    continue

                lyric_text = clean_lyric_text(raw_lrc)
                if lyric_text:
                    return song_name, artist_display, lyric_text, "QQ音乐"

            return None

        try:
            return await loop.run_in_executor(None, _search_and_get)
        except Exception as e:
            print(f"歌词搜索出错: {e}")
            return None

    async def _fetch_lyrics(
        self, keyword: str
    ) -> tuple[str, str, str, str] | None:
        """Search QQ Music first, then use LRCLIB as a fallback."""
        result = await self._fetch_qq_lyrics(keyword)
        if result:
            return result
        return await fetch_lrclib_lyrics(keyword)

    @staticmethod
    def _extract_lyrics_candidates(title: str) -> list[str]:
        """
        从B站等视频标题中智能提取多个歌词搜索候选词，按优先级排序。
        返回一个候选列表，调用方依次尝试直到搜到歌词。

        例:
          "在百万豪装录音棚大声听 李常超《盗墓笔记·十年人间》【Hi-res】"
          → ["李常超 盗墓笔记·十年人间", "盗墓笔记·十年人间", "盗墓笔记 十年人间"]

          "【4K】周杰伦《稻香》官方MV"
          → ["周杰伦 稻香", "稻香"]

          "稻香 - 周杰伦｜歌词版Lyric Video"
          → ["稻香 周杰伦", "稻香"]
        """
        candidates = []

        # ─── 翻唱/AI标记检测 ───
        # 如果提取到的"歌手"实际上是翻唱者/AI歌手，不要拿它来搜歌词
        COVER_INDICATORS = [
            "AI", "ai", "翻唱", "cover", "Cover", "COVER",
            "东雪莲", "洛天依", "初音", "ミク", "VOCALOID",
            "remix", "Remix", "改编", "自制",
        ]

        def _is_cover_artist(name: str) -> bool:
            return any(tag in name for tag in COVER_INDICATORS)

        # ─── 策略1: 提取《》里的歌名 + 前面可能的歌手名 ───
        song_in_brackets = None
        artist_maybe = None

        # 模式A: 【artist】《song》 (如 【AI东雪莲】《大雨还在下》)
        bracket_match = re.search(
            r"[【\[]([^\]】]+)[】\]]\s*[《](.+?)[》]", title
        )
        # 模式B: artist《song》 (如 周杰伦《稻香》)
        plain_match = re.search(
            r"([\u4e00-\u9fff\w]{2,8})\s*[《](.+?)[》]", title
        )
        # 模式C: 只有《song》
        bare_match = re.search(r"[《](.+?)[》]", title)

        if bracket_match:
            artist_maybe = bracket_match.group(1).strip()
            song_in_brackets = bracket_match.group(2).strip()
        elif plain_match:
            artist_maybe = plain_match.group(1).strip()
            song_in_brackets = plain_match.group(2).strip()
        elif bare_match:
            song_in_brackets = bare_match.group(1).strip()

        if song_in_brackets:
            if artist_maybe and _is_cover_artist(artist_maybe):
                # 翻唱者/AI歌手，优先纯歌名搜索，不带翻唱者名字
                candidates.append(song_in_brackets)
                candidates.append(f"{song_in_brackets} 原唱")
            elif artist_maybe:
                # 可能是原唱歌手，"歌手 歌名" 是最佳搜索词
                candidates.append(f"{artist_maybe} {song_in_brackets}")
            # 纯歌名也作为备选
            if song_in_brackets not in candidates:
                candidates.append(song_in_brackets)
            # 如果歌名中有中文标点（如·），拆开试试
            if artist_maybe and (
                "·" in song_in_brackets or "·" in song_in_brackets
            ):
                cleaned = song_in_brackets.replace("·", " ").replace(
                    "·", " "
                )
                if not _is_cover_artist(artist_maybe):
                    candidates.append(f"{artist_maybe} {cleaned}")
                candidates.append(cleaned)

        # ─── 策略2: 通用清洗后的完整标题 ───
        t = title
        t = re.sub(r"[【\[].*?[】\]]", " ", t)
        t = re.sub(r"[《](.+?)[》]", r" \1 ", t)
        t = re.sub(r"[「](.+?)[」]", r" \1 ", t)
        t = re.sub(
            r"\((?:官方|official|MV|lyric|歌词|live|翻唱|cover|"
            r"feat\.?|完整版|高清|HD|4K|1080p|视频|audio|"
            r"动态歌词|字幕|中文|日文|英文|高音质)[^)]*\)",
            " ", t, flags=re.IGNORECASE,
        )
        t = re.sub(r"\([^)]{10,}\)", " ", t)
        for tag in [
            "MV", "PV", "官方", "Official", "Lyric Video",
            "歌词版", "完整版", "高清", "4K", "1080P", "Hi-res",
            "翻唱", "Cover", "cover", "Live", "live",
            "动态歌词", "无损", "HQ", "HD", "Hi-Res", "hi-res",
        ]:
            t = t.replace(tag, " ")
        t = re.sub(r"[｜|／/\\～~—–_]", " ", t)
        t = t.replace(" - ", " ").replace("-", " ")
        t = re.sub(r"\s+", " ", t).strip()
        if len(t) >= 2 and t not in candidates:
            candidates.append(t)

        # ─── 策略3: "歌名 - 歌手" 或 "歌手 - 歌名" 格式 ───
        dash_match = re.match(
            r"^(.+?)\s*[-–—]\s*(.+?)(?:\s|$)", title
        )
        if dash_match:
            part1 = dash_match.group(1).strip()
            part2 = dash_match.group(2).strip()
            combo = f"{part1} {part2}"
            if combo not in candidates:
                candidates.append(combo)

        # ─── 策略4: 如果清洗结果有多段，只取最短的那段（可能是歌名） ───
        if t and " " in t:
            parts = t.split()
            # 找最短的中文部分（≥2字），可能就是歌名
            cn_parts = [
                p for p in parts
                if len(p) >= 2 and re.search(r"[\u4e00-\u9fff]", p)
            ]
            if cn_parts:
                shortest = min(cn_parts, key=len)
                if shortest not in candidates:
                    candidates.append(shortest)

        # 去重并保持顺序
        seen = set()
        unique = []
        for c in candidates:
            c = c.strip()
            if c and c not in seen:
                seen.add(c)
                unique.append(c)

        # 兜底：如果一个候选都没有，用原标题
        if not unique:
            unique.append(title.strip())

        return unique

    _extract_lyrics_candidates = staticmethod(extract_lyrics_candidates)

    async def _find_lyrics_for_title(
        self, title: str
    ) -> tuple[str, str, str, str] | None:
        """Try cleaned title candidates until a matching lyric is found."""
        for candidate in self._extract_lyrics_candidates(title):
            cleaned = re.sub(r"[^\w\u4e00-\u9fff]", "", candidate)
            if len(cleaned) < 2:
                continue
            result = await self._fetch_lyrics(candidate)
            if result:
                return result
        return None

    @staticmethod
    def _create_lyrics_embed(
        result: tuple[str, str, str, str], *, automatic: bool = False
    ) -> discord.Embed:
        song_name, artists, lyric_text, source = result
        embed = discord.Embed(
            title=f"🎤 {song_name}",
            description=(
                lyric_text
                if len(lyric_text) <= 4000
                else lyric_text[:4000] + "\n\n*... 歌词过长已截断*"
            ),
            color=discord.Color.gold(),
        )
        embed.set_author(name=artists)
        footer = f"歌词来源: {source}"
        if automatic:
            footer += " · 自动歌词"
        embed.set_footer(text=footer)
        return embed

    async def _send_auto_lyrics(
        self, ctx: commands.Context, song: Song
    ) -> None:
        result = await self._find_lyrics_for_title(song.title)
        player = self.get_player(ctx.guild.id)
        if player.current is not song or not player.auto_lyrics:
            return
        if not result:
            await ctx.send(
                f"🎤 未找到 **{song.title}** 的匹配歌词，继续播放。"
            )
            return
        await ctx.send(embed=self._create_lyrics_embed(result, automatic=True))

    @commands.hybrid_command(
        name="自动歌词",
        aliases=["autolyrics", "歌词开关"],
        help="开启或关闭换歌时自动显示歌词",
    )
    @app_commands.describe(state="开/关；留空则切换当前状态")
    async def auto_lyrics(self, ctx: commands.Context, state: str = ""):
        player = self.get_player(ctx.guild.id)
        normalized = state.strip().lower()
        enabled_values = {"开", "开启", "打开", "on", "true", "1"}
        disabled_values = {"关", "关闭", "off", "false", "0"}
        if not normalized:
            player.auto_lyrics = not player.auto_lyrics
        elif normalized in enabled_values:
            player.auto_lyrics = True
        elif normalized in disabled_values:
            player.auto_lyrics = False
        else:
            return await ctx.send("❌ 参数应为 `开` 或 `关`。")
        status = "开启" if player.auto_lyrics else "关闭"
        await ctx.send(f"🎤 自动歌词已{status}。")

    @commands.hybrid_command(
        name="歌词",
        aliases=["lyrics", "lrc", "词"],
        help="显示当前歌曲或指定歌曲的歌词",
    )
    @app_commands.describe(keyword="搜索歌词的关键词（不填则搜索当前播放的歌）")
    async def lyrics(
        self, ctx: commands.Context, *, keyword: str = ""
    ):
        player = self.get_player(ctx.guild.id)

        # 没提供关键词就用当前播放的歌名
        auto_mode = False
        if not keyword:
            if player.current:
                auto_mode = True
                raw_title = player.current.title
            else:
                return await ctx.send(
                    "❌ 当前没有播放歌曲，请提供搜索关键词\n"
                    "例: `！歌词 稻香`"
                )

        async with ctx.typing():
            if auto_mode:
                result = await self._find_lyrics_for_title(raw_title)
            else:
                result = await self._fetch_lyrics(keyword)

        if not result:
            if auto_mode:
                # 自动模式搜不到: 可能是B站原创/小众内容
                return await ctx.send(
                    f"❌ 未能找到匹配的歌词\n"
                    f"当前播放: **{raw_title}**\n\n"
                    "可能原因:\n"
                    "• 这首歌是原创/二创内容，当前歌词源均未收录\n"
                    "• 标题中的歌名格式无法自动识别\n\n"
                    "你可以手动指定歌名: `！歌词 <歌名>`"
                )
            else:
                return await ctx.send(
                    f"❌ 找不到 **{keyword}** 的歌词\n"
                    "请检查歌名是否正确，或尝试加上歌手名: "
                    "`！歌词 歌手 歌名`"
                )

        await ctx.send(embed=self._create_lyrics_embed(result))


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
