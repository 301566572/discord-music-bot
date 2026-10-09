"""Bilibili API helpers."""
from cogs.services.http import request_json


BILI_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com/",
}


def archive_to_entry(item: dict) -> dict:
    bvid = item.get("bvid", "")
    return {
        "title": item.get("title", "未知"),
        "url": f"https://www.bilibili.com/video/{bvid}" if bvid else "",
        "duration": item.get("duration", 0),
    }


def fetch_favorite_entries(media_id: str, cookies: dict) -> list[dict] | None:
    """Fetch a Bilibili favorite list using the public API."""
    results = []
    page = 1
    while True:
        data = request_json(
            "GET",
            "https://api.bilibili.com/x/v3/fav/resource/list",
            params={
                "media_id": media_id,
                "pn": page,
                "ps": 20,
                "platform": "web",
            },
            headers=BILI_HEADERS,
            cookies=cookies,
            timeout=15,
        )
        if data.get("code") != 0:
            return None if not results else results

        medias = data.get("data", {}).get("medias", [])
        if not medias:
            break

        results.extend(archive_to_entry(item) for item in medias)

        info = data.get("data", {}).get("info", {})
        total = info.get("media_count", 0)
        if len(results) >= total:
            break
        page += 1

    return results


def fetch_collection_entries(collection_info: dict, cookies: dict) -> tuple[str, list[dict]]:
    """Fetch Bilibili season/series entries."""
    if not collection_info:
        return "", []

    results = []
    collection_name = "B站合集"

    if "season_id" in collection_info:
        mid = collection_info["mid"]
        sid = collection_info["season_id"]
        page = 1
        while True:
            data = request_json(
                "GET",
                "https://api.bilibili.com/x/polymer/web-space/"
                "seasons_archives_list",
                params={
                    "mid": mid,
                    "season_id": sid,
                    "page_num": page,
                    "page_size": 30,
                },
                headers=BILI_HEADERS,
                cookies=cookies,
                timeout=15,
            )
            if data.get("code") != 0:
                break

            archives_data = data.get("data", {})
            meta = archives_data.get("meta", {})
            collection_name = meta.get("name", "B站合集")
            archives = archives_data.get("archives", [])
            if not archives:
                break

            results.extend(archive_to_entry(item) for item in archives)

            page_info = archives_data.get("page", {})
            total = page_info.get("total", 0)
            if len(results) >= total:
                break
            page += 1

    elif "series_id" in collection_info:
        mid = collection_info["mid"]
        sid = collection_info["series_id"]
        page = 1
        while True:
            data = request_json(
                "GET",
                "https://api.bilibili.com/x/series/archives",
                params={
                    "mid": mid,
                    "series_id": sid,
                    "pn": page,
                    "ps": 30,
                    "sort": "asc",
                },
                headers=BILI_HEADERS,
                cookies=cookies,
                timeout=15,
            )
            if data.get("code") != 0:
                break

            archives = data.get("data", {}).get("archives", [])
            if not archives:
                break

            results.extend(archive_to_entry(item) for item in archives)

            meta_data = request_json(
                "GET",
                "https://api.bilibili.com/x/series/series",
                params={"series_id": sid},
                headers=BILI_HEADERS,
                timeout=10,
            )
            meta = meta_data.get("data", {}).get("meta", {})
            collection_name = meta.get("name", "B站系列")
            total = meta.get("total", 0)
            if len(results) >= total:
                break
            page += 1

    return collection_name, results
