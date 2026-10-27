"""Shared yt-dlp extraction helpers."""
import asyncio
from collections.abc import Mapping

import yt_dlp

from cogs.services.bili_audio import fetch_public_audio, public_video_query


async def extract_first(query: str, options: Mapping) -> dict | None:
    """Run yt-dlp and return the first entry when the result is a playlist."""
    loop = asyncio.get_running_loop()
    ydl_options = dict(options)

    def _extract():
        try:
            with yt_dlp.YoutubeDL(ydl_options) as ydl:
                info = ydl.extract_info(query, download=False)
                if info and "entries" in info:
                    entries = list(info["entries"])
                    return entries[0] if entries else None
                return info
        except yt_dlp.utils.DownloadError:
            if public_video_query(query) is None:
                raise
            # A fresh anonymous API request; never borrow another user's cookies.
            return fetch_public_audio(query)

    return await loop.run_in_executor(None, _extract)
