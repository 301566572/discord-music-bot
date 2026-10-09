"""Shared yt-dlp extraction helpers."""
import asyncio
from collections.abc import Mapping

import yt_dlp


async def extract_first(query: str, options: Mapping) -> dict | None:
    """Run yt-dlp and return the first entry when the result is a playlist."""
    loop = asyncio.get_running_loop()
    ydl_options = dict(options)

    def _extract():
        with yt_dlp.YoutubeDL(ydl_options) as ydl:
            info = ydl.extract_info(query, download=False)
            if info and "entries" in info:
                entries = list(info["entries"])
                return entries[0] if entries else None
            return info

    return await loop.run_in_executor(None, _extract)
