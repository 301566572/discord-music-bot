"""Fallback lyrics providers shared by music commands."""
import asyncio
import re
from collections.abc import Callable
from typing import Any

from cogs.services.http import request_json


LRCLIB_URL = "https://lrclib.net/api/search"
LRCLIB_HEADERS = {
    "User-Agent": (
        "discord-music-bot/1.0 "
        "(https://github.com/301566572/discord-music-bot)"
    )
}


def clean_lyric_text(text: str) -> str:
    """Remove LRC timestamps and metadata while preserving lyric lines."""
    text = re.sub(r"<[^>]+>", "", text or "")
    lines = []
    for line in text.splitlines():
        line = re.sub(r"\[[\d:.]+\]", "", line).strip()
        line = re.sub(r"\[[a-z]+:.*?\]", "", line, flags=re.IGNORECASE).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def lrclib_record_to_result(record: dict) -> tuple[str, str, str, str] | None:
    """Normalize one LRCLIB record to the bot's lyrics result shape."""
    if record.get("instrumental"):
        return None
    lyric_text = clean_lyric_text(
        record.get("plainLyrics") or record.get("syncedLyrics") or ""
    )
    if not lyric_text:
        return None
    return (
        record.get("trackName") or record.get("name") or "未知歌曲",
        record.get("artistName") or "未知歌手",
        lyric_text,
        "LRCLIB",
    )


async def fetch_lrclib_lyrics(
    keyword: str,
    *,
    requester: Callable[..., Any] | None = None,
) -> tuple[str, str, str, str] | None:
    """Search LRCLIB and return the first result containing lyrics."""
    loop = asyncio.get_running_loop()

    def _fetch():
        try:
            records = request_json(
                "GET",
                LRCLIB_URL,
                params={"q": keyword},
                headers=LRCLIB_HEADERS,
                timeout=10,
                retries=1,
                requester=requester,
            )
        except Exception:
            return None
        if not isinstance(records, list):
            return None
        for record in records:
            if isinstance(record, dict):
                result = lrclib_record_to_result(record)
                if result:
                    return result
        return None

    return await loop.run_in_executor(None, _fetch)
