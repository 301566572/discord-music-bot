"""Anonymous fallback for public Bilibili video links."""
import re
from urllib.parse import parse_qs, urlsplit

from cogs.services.http import request_json


HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.bilibili.com/"}


def public_video_query(url: str) -> dict | None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
        "www.bilibili.com", "bilibili.com", "m.bilibili.com",
    }:
        return None
    match = re.fullmatch(r"/video/(BV[0-9A-Za-z]+|av\d+)/?", parsed.path)
    if not match:
        return None
    video_id = match.group(1)
    return {"bvid": video_id} if video_id.startswith("BV") else {"aid": video_id[2:]}


def fetch_public_audio(url: str, *, requester=None) -> dict | None:
    """Resolve public audio without reading or sending any account cookies."""
    query = public_video_query(url)
    if query is None:
        return None

    def get(path, params):
        result = request_json(
            "GET", f"https://api.bilibili.com/{path}", params=params,
            headers=HEADERS, timeout=15, retries=0, requester=requester,
        )
        if not isinstance(result, dict) or result.get("code") != 0:
            raise ValueError("B站公开视频接口暂不可用或视频受限")
        return result.get("data") or {}

    video = get("x/web-interface/wbi/view", query)
    page = int(parse_qs(urlsplit(url).query).get("p", ["1"])[0])
    pages = video.get("pages") or [{"cid": video.get("cid"), "duration": video.get("duration")}]
    if page < 1 or page > len(pages):
        raise ValueError("B站分P不存在")
    selected = pages[page - 1]
    if not selected.get("cid"):
        raise ValueError("B站视频缺少分P信息")
    play = get("x/player/wbi/playurl", {
        **query, "cid": selected["cid"], "fnval": 4048, "fnver": 0, "fourk": 1,
    })
    audio = [item for item in (play.get("dash") or {}).get("audio", [])
             if item.get("baseUrl") or item.get("base_url")]
    if not audio:
        raise ValueError("B站未提供可匿名播放的音频")
    best = max(audio, key=lambda item: item.get("bandwidth") or 0)
    return {
        "url": best.get("baseUrl") or best["base_url"],
        "title": video.get("title", "B站视频"),
        "webpage_url": f"https://www.bilibili.com/video/{video.get('bvid', next(iter(query.values())))}/?p={page}",
        "duration": selected.get("duration") or video.get("duration", 0),
        "thumbnail": video.get("pic", ""),
        "http_headers": HEADERS.copy(),
    }
