"""NetEase playlist service."""
import asyncio

from cogs.services.http import request_json


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://music.163.com/",
    "Content-Type": "application/x-www-form-urlencoded",
}


def track_to_song(track: dict) -> dict:
    """Normalize a NetEase track object into the bot song shape."""
    song_name = track.get("name", "")
    artist_items = track.get("ar") or track.get("artists") or []
    artists = " ".join(a.get("name", "") for a in artist_items)
    duration = (track.get("dt") or track.get("duration") or 0) // 1000
    return {
        "name": song_name,
        "artist": artists,
        "duration": duration,
        "query": f"{song_name} {artists}".strip(),
    }


async def fetch_playlist(playlist_id: str) -> tuple[str, list[dict]]:
    """Fetch a NetEase playlist, returning (playlist_name, normalized_songs)."""
    loop = asyncio.get_running_loop()

    def _fetch():
        data = request_json(
            "POST",
            "https://music.163.com/api/v6/playlist/detail",
            headers=HEADERS,
            data={"id": playlist_id, "n": 10000},
            timeout=15,
        )
        playlist_info = data.get("playlist", {})
        name = playlist_info.get("name", "未知歌单")
        tracks = playlist_info.get("tracks", [])
        track_ids = playlist_info.get("trackIds", [])

        if tracks and tracks[0].get("name") and len(tracks) >= len(track_ids):
            return name, [track_to_song(track) for track in tracks]

        if not track_ids:
            return name, []

        songs = []
        ids_list = [track.get("id") for track in track_ids if track.get("id")]
        for index in range(0, len(ids_list), 500):
            batch = ids_list[index:index + 500]
            ids_str = ",".join(str(item) for item in batch)
            detail_data = request_json(
                "POST",
                "https://music.163.com/api/song/detail",
                headers=HEADERS,
                data={"ids": f"[{ids_str}]"},
                timeout=15,
            )
            songs.extend(
                track_to_song(song) for song in detail_data.get("songs", [])
            )
        return name, songs

    return await loop.run_in_executor(None, _fetch)
