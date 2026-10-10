"""Small offline harness for pure project logic.

Run:
    python harness.py
"""
import unittest
from collections import deque
from tempfile import TemporaryDirectory
from pathlib import Path
from types import SimpleNamespace

from cogs.game_logic import calculate_clip_window, check_answer, normalize
from cogs.lyrics_utils import extract_lyrics_candidates
from cogs.playlist_parsers import (
    clean_search_query,
    extract_bili_collection_info,
    extract_bili_fav_id,
    extract_netease_id,
    is_bili_url,
)
from cogs.services.cookies import parse_netscape_cookie_file
from cogs.services.cookies import replace_cookie_file, validate_bili_cookie_text
from cogs.services.diagnostics import format_checks
from cogs.services.http import request_json
from cogs.services.lyrics import (
    clean_lyric_text,
    fetch_lrclib_lyrics,
    lrclib_record_to_result,
)
from cogs.services.netease import track_to_song
from cogs.services.bilibili import archive_to_entry
import cogs.services.queue_snapshot as queue_snapshot
from cogs.services.queue_snapshot import (
    append_named_queue_record,
    create_named_queue,
    delete_named_queue,
    list_named_queues,
    load_named_queue,
    sanitize_queue_name,
    save_named_queue,
    validate_snapshot,
)


class BotCommandHarness(unittest.TestCase):
    def test_help_command_prefix_alias_and_slash_registration(self):
        import bot as bot_module

        bot = bot_module.bot

        help_command = bot.get_command("帮助")
        self.assertIsNotNone(help_command)
        self.assertIs(bot.get_command("help"), help_command)
        self.assertIsNotNone(bot.tree.get_command("帮助"))
        self.assertIsNotNone(bot.get_command("帮助网页"))
        self.assertIsNotNone(bot.tree.get_command("帮助网页"))

        embed = bot_module.build_basic_help_embed()
        help_text = "\n".join(field.value for field in embed.fields)
        self.assertEqual(len(embed.fields), 3)
        self.assertIn("！播放 <歌名/链接>", help_text)
        self.assertIn("！播放歌单 <名称>", help_text)
        self.assertIn("！帮助网页", help_text)
        self.assertNotIn("！导出队列", help_text)
        self.assertNotIn("！设置cookies", help_text)

    def test_public_help_url_validation(self):
        import bot as bot_module

        original = bot_module.HELP_URL
        try:
            bot_module.HELP_URL = ""
            self.assertIsNone(bot_module._public_help_url())
            bot_module.HELP_URL = "file:///help/index.html"
            self.assertIsNone(bot_module._public_help_url())
            bot_module.HELP_URL = "https://example.com/help"
            self.assertEqual(
                bot_module._public_help_url(),
                "https://example.com/help",
            )
        finally:
            bot_module.HELP_URL = original


class PlaylistConversationHarness(unittest.IsolatedAsyncioTestCase):
    async def test_interactive_playlist_creation(self):
        from cogs.music import Music

        author = SimpleNamespace(id=7, bot=False)
        channel = SimpleNamespace(id=8)
        messages = iter([
            SimpleNamespace(content="通勤", author=author, channel=channel),
            SimpleNamespace(content="稻香 周杰伦", author=author, channel=channel),
            SimpleNamespace(content="完成歌单", author=author, channel=channel),
        ])

        class FakeBot:
            async def wait_for(self, event, check, timeout):
                self_event = next(messages)
                if event != "message" or not check(self_event):
                    raise AssertionError("playlist input check failed")
                return self_event

        class FakeContext:
            def __init__(self):
                self.guild = SimpleNamespace(id=9)
                self.author = author
                self.channel = channel
                self.sent = []

            async def send(self, content=None, **kwargs):
                self.sent.append(content)

        music = Music(FakeBot())

        async def resolve(query, requester_id):
            return {
                "source_url": None,
                "title": "稻香 - 周杰伦",
                "webpage_url": "https://example.invalid/song",
                "duration": 223,
                "thumbnail": "",
                "is_bili": False,
                "search_query": query,
            }

        music._resolve_playlist_record = resolve
        ctx = FakeContext()
        with TemporaryDirectory() as tmp:
            old_dir = queue_snapshot.QUEUE_STORE_DIR
            queue_snapshot.QUEUE_STORE_DIR = Path(tmp)
            try:
                await Music.create_playlist.callback(music, ctx)
                payload = load_named_queue(9, "通勤")
                self.assertEqual(len(payload["queue"]), 1)
                self.assertEqual(payload["queue"][0]["title"], "稻香 - 周杰伦")
                self.assertIn("创建完成", ctx.sent[-1])
            finally:
                queue_snapshot.QUEUE_STORE_DIR = old_dir

    async def test_playlist_pager_content_and_pages(self):
        from cogs.music import PlaylistPager

        records = [
            {
                "title": f"歌曲 {index}",
                "duration": 60,
                "webpage_url": "",
            }
            for index in range(1, 13)
        ]
        view = PlaylistPager("测试歌单", records, requester_id=7)
        self.assertEqual(view.page_count, 2)
        first_page = view.create_embed()
        self.assertIn("歌曲 1", first_page.description)
        self.assertNotIn("歌曲 11", first_page.description)
        view.page = 1
        view._sync_buttons()
        second_page = view.create_embed()
        self.assertIn("歌曲 11", second_page.description)
        self.assertEqual(second_page.footer.text, "第 2/2 页")


class ParserHarness(unittest.TestCase):
    def test_bili_url_detection(self):
        self.assertTrue(is_bili_url("https://www.bilibili.com/video/BV123"))
        self.assertTrue(is_bili_url("https://b23.tv/abc123"))
        self.assertFalse(is_bili_url("https://youtube.com/watch?v=abc"))

    def test_bili_playlist_ids(self):
        self.assertEqual(
            extract_bili_fav_id(
                "https://space.bilibili.com/1/favlist?fid=67890"
            ),
            "67890",
        )
        self.assertEqual(
            extract_bili_fav_id("https://www.bilibili.com/list/ml24680"),
            "24680",
        )

    def test_bili_collection_ids(self):
        self.assertEqual(
            extract_bili_collection_info(
                "https://space.bilibili.com/12/lists/34?type=series"
            ),
            {"mid": "12", "series_id": "34"},
        )
        self.assertEqual(
            extract_bili_collection_info(
                "https://space.bilibili.com/12/channel/collectiondetail?sid=34"
            ),
            {"mid": "12", "season_id": "34"},
        )

    def test_netease_id(self):
        self.assertEqual(extract_netease_id("12345"), "12345")
        self.assertEqual(
            extract_netease_id("https://music.163.com/playlist?id=9988"),
            "9988",
        )
        self.assertIsNone(extract_netease_id("not a playlist"))

    def test_search_cleaning(self):
        self.assertEqual(clean_search_query("【4K】周杰伦《稻香》官方MV"), "稻香 周杰伦")
        self.assertEqual(clean_search_query("稻香"), "稻香")


class LyricsHarness(unittest.TestCase):
    def test_extracts_bracketed_song_and_artist(self):
        self.assertEqual(
            extract_lyrics_candidates("【4K】周杰伦《稻香》官方MV")[:2],
            ["周杰伦 稻香", "稻香"],
        )

    def test_cover_artist_prefers_song_name(self):
        self.assertEqual(
            extract_lyrics_candidates("【AI东雪莲】《大雨还在下》")[0],
            "大雨还在下",
        )

    def test_lrc_cleanup_and_lrclib_normalization(self):
        self.assertEqual(
            clean_lyric_text("[ar:测试]\n[00:01.00]第一句\n[00:02.50]第二句"),
            "第一句\n第二句",
        )
        result = lrclib_record_to_result({
            "trackName": "测试歌曲",
            "artistName": "测试歌手",
            "syncedLyrics": "[00:01.00]测试歌词",
        })
        self.assertEqual(
            result,
            ("测试歌曲", "测试歌手", "测试歌词", "LRCLIB"),
        )


class LyricsProviderHarness(unittest.IsolatedAsyncioTestCase):
    async def test_lrclib_fetcher_uses_first_usable_result(self):
        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return [
                    {"instrumental": True},
                    {
                        "trackName": "稻香",
                        "artistName": "周杰伦",
                        "plainLyrics": "对这个世界如果你有太多的抱怨",
                    },
                ]

        def requester(method, url, **kwargs):
            self.assertEqual(kwargs["params"], {"q": "稻香 周杰伦"})
            self.assertIn("discord-music-bot", kwargs["headers"]["User-Agent"])
            return FakeResponse()

        result = await fetch_lrclib_lyrics(
            "稻香 周杰伦", requester=requester
        )
        self.assertEqual(result[0], "稻香")
        self.assertEqual(result[3], "LRCLIB")


class MultiSourceSearchHarness(unittest.IsolatedAsyncioTestCase):
    async def test_song_search_falls_back_from_youtube_to_bilibili(self):
        from cogs.music import Music

        music = Music(SimpleNamespace())
        calls = []

        async def search(query, bili_mode=False, user_id=None):
            calls.append((query, bili_mode, user_id))
            if bili_mode:
                return {"url": "https://audio.invalid/bili"}
            return None

        music._search = search
        info, is_bili, source = await music._search_music_sources(
            "冷门歌曲", user_id=7
        )
        self.assertEqual(info["url"], "https://audio.invalid/bili")
        self.assertTrue(is_bili)
        self.assertEqual(source, "B站")
        self.assertEqual(
            calls,
            [("冷门歌曲", False, None), ("冷门歌曲", True, 7)],
        )

    async def test_explicit_bilibili_search_does_not_try_youtube(self):
        from cogs.music import Music

        music = Music(SimpleNamespace())
        calls = []

        async def search(query, bili_mode=False, user_id=None):
            calls.append((query, bili_mode, user_id))
            return None

        music._search = search
        await music._search_music_sources(
            "只搜B站", user_id=8, prefer_bili=True
        )
        self.assertEqual(calls, [("只搜B站", True, 8)])


class GameLogicHarness(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize("  Lemon! "), "lemon")
        self.assertEqual(normalize("青 花 瓷"), "青花瓷")

    def test_answer_matching(self):
        self.assertTrue(check_answer("qingtian", "晴天", "周杰伦"))
        self.assertTrue(check_answer("周杰伦 青花瓷", "青花瓷", "周杰伦"))
        self.assertFalse(check_answer("周杰伦", "晴天", "周杰伦"))

    def test_clip_window_uses_middle_for_long_songs(self):
        self.assertEqual(calculate_clip_window(240, 45), (72, 45))

    def test_clip_window_stays_safe_for_short_or_unknown_songs(self):
        self.assertEqual(calculate_clip_window(50, 45), (0, 45))
        self.assertEqual(calculate_clip_window(30, 45), (0, 30))
        self.assertEqual(calculate_clip_window(None, 40), (0, 40))


class GamePlaybackHarness(unittest.IsolatedAsyncioTestCase):
    async def test_guess_game_prefers_bilibili_then_falls_back(self):
        from cogs.game import MusicGame

        class FakeMusic:
            def __init__(self):
                self.calls = []

            async def _search(self, query, bili_mode=False, user_id=None):
                self.calls.append((query, bili_mode, user_id))
                if bili_mode:
                    return None
                return {"url": "https://audio.invalid/fallback"}

        music = FakeMusic()
        bot = SimpleNamespace(
            get_cog=lambda name: music if name == "🎵 音乐" else None
        )
        game_cog = MusicGame(bot)
        info, is_bili = await game_cog._search_song("周杰伦 稻香", user_id=7)

        self.assertEqual(info["url"], "https://audio.invalid/fallback")
        self.assertFalse(is_bili)
        self.assertEqual(
            music.calls,
            [("周杰伦 稻香", True, 7), ("周杰伦 稻香", False, None)],
        )

    async def test_guess_game_temporarily_preserves_music_queue(self):
        from cogs.game import GuessGame, MusicGame

        player = SimpleNamespace(
            current="current",
            queue=deque(["next"]),
            volume=0.7,
            auto_lyrics=True,
            loop=True,
            loop_queue=False,
            intentional_stop=False,
            external_control=False,
        )

        class FakeMusic:
            def __init__(self):
                self.restored = False

            def get_player(self, guild_id):
                self.guild_id = guild_id
                return player

            async def _async_play_next(self, ctx):
                self.restored = True

        class FakeVoice:
            def __init__(self):
                self.playing = True

            def is_playing(self):
                return self.playing

            def is_paused(self):
                return False

            def is_connected(self):
                return True

            def stop(self):
                self.playing = False

        music = FakeMusic()
        bot = SimpleNamespace(
            get_cog=lambda name: music if name == "🎵 音乐" else None
        )
        game_cog = MusicGame(bot)
        game = GuessGame(None, None)
        ctx = SimpleNamespace(guild=SimpleNamespace(id=9))
        vc = FakeVoice()

        await game_cog._claim_music_player(ctx, game, vc)
        self.assertIsNone(player.current)
        self.assertEqual(list(player.queue), [])
        self.assertTrue(player.external_control)
        self.assertEqual(game.saved_music_state["songs"], ["current", "next"])

        self.assertTrue(await game_cog._restore_music_player(ctx, game, vc))
        self.assertEqual(list(player.queue), ["current", "next"])
        self.assertFalse(player.external_control)
        self.assertTrue(music.restored)


class ServiceHarness(unittest.TestCase):
    def test_cookie_file_parser(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "cookies.txt"
            path.write_text(
                "# Netscape HTTP Cookie File\n"
                ".bilibili.com\tTRUE\t/\tFALSE\t0\tSESSDATA\tabc\n"
                ".bilibili.com\tTRUE\t/\tFALSE\t0\tbili_jct\tdef\n",
                encoding="utf-8",
            )
            self.assertEqual(
                parse_netscape_cookie_file(path),
                {"SESSDATA": "abc", "bili_jct": "def"},
            )

    def test_cookie_validation_and_replacement(self):
        text = ".bilibili.com\tTRUE\t/\tFALSE\t0\tSESSDATA\tabc\n"
        self.assertEqual(validate_bili_cookie_text(text), {"SESSDATA": "abc"})
        with self.assertRaises(ValueError):
            validate_bili_cookie_text(".bilibili.com\tTRUE\t/\tFALSE\t0\tDedeUserID\t1\n")

        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "cookies.txt"
            path.write_text("old", encoding="utf-8")
            self.assertTrue(replace_cookie_file(path, b"new"))
            self.assertEqual(path.read_text(encoding="utf-8"), "new")

    def test_diagnostic_formatter(self):
        self.assertEqual(
            format_checks([("FFmpeg", True, "C:/ffmpeg/bin/ffmpeg.exe")]),
            "`OK` **FFmpeg**: C:/ffmpeg/bin/ffmpeg.exe",
        )

    def test_netease_track_normalization(self):
        self.assertEqual(
            track_to_song({
                "name": "稻香",
                "ar": [{"name": "周杰伦"}],
                "dt": 223000,
            }),
            {
                "name": "稻香",
                "artist": "周杰伦",
                "duration": 223,
                "query": "稻香 周杰伦",
            },
        )

    def test_request_json_uses_injected_requester(self):
        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {"ok": True}

        calls = []

        def requester(method, url, **kwargs):
            calls.append((method, url, kwargs["timeout"]))
            return Response()

        self.assertEqual(
            request_json(
                "GET",
                "https://example.invalid/test",
                requester=requester,
                timeout=3,
            ),
            {"ok": True},
        )
        self.assertEqual(calls, [("GET", "https://example.invalid/test", 3)])

    def test_bilibili_archive_normalization(self):
        self.assertEqual(
            archive_to_entry({
                "bvid": "BV123",
                "title": "测试视频",
                "duration": 66,
            }),
            {
                "title": "测试视频",
                "url": "https://www.bilibili.com/video/BV123",
                "duration": 66,
            },
        )

    def test_queue_snapshot_validation(self):
        payload = {
            "version": 1,
            "queue": [{"title": "稻香", "duration": 223}],
        }
        self.assertEqual(validate_snapshot(payload), payload["queue"])
        with self.assertRaises(ValueError):
            validate_snapshot({"version": 999, "queue": []})

    def test_named_queue_storage(self):
        payload = {
            "version": 1,
            "current": None,
            "queue": [{"title": "稻香", "duration": 223}],
        }
        with TemporaryDirectory() as tmp:
            old_dir = queue_snapshot.QUEUE_STORE_DIR
            queue_snapshot.QUEUE_STORE_DIR = Path(tmp)
            try:
                path = save_named_queue(123, "周杰伦/测试", payload)
                self.assertEqual(path.stem, "周杰伦_测试")
                self.assertEqual(list_named_queues(123), ["周杰伦_测试"])
                self.assertEqual(load_named_queue(123, "周杰伦_测试"), payload)
                self.assertEqual(delete_named_queue(123, "周杰伦_测试"), "周杰伦_测试")
                self.assertEqual(list_named_queues(123), [])
            finally:
                queue_snapshot.QUEUE_STORE_DIR = old_dir

    def test_create_and_append_named_playlist(self):
        record = {
            "source_url": None,
            "title": "稻香",
            "webpage_url": "https://example.invalid/song",
            "duration": 223,
            "thumbnail": "",
            "is_bili": False,
            "search_query": "稻香 周杰伦",
        }
        with TemporaryDirectory() as tmp:
            old_dir = queue_snapshot.QUEUE_STORE_DIR
            queue_snapshot.QUEUE_STORE_DIR = Path(tmp)
            try:
                path = create_named_queue(123, "通勤")
                self.assertEqual(path.stem, "通勤")
                with self.assertRaises(FileExistsError):
                    create_named_queue(123, "通勤")
                _, total = append_named_queue_record(123, "通勤", record)
                self.assertEqual(total, 1)
                self.assertEqual(
                    load_named_queue(123, "通勤")["queue"], [record]
                )
            finally:
                queue_snapshot.QUEUE_STORE_DIR = old_dir

    def test_queue_name_sanitizer(self):
        self.assertEqual(sanitize_queue_name("  ../我的 歌单  "), "我的_歌单")
        with self.assertRaises(ValueError):
            sanitize_queue_name("...   ")


if __name__ == "__main__":
    unittest.main(verbosity=2)
