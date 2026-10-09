"""Pure parsing helpers for music commands."""
import re


BILI_URL_PATTERN = re.compile(
    r"(https?://)?(www\.)?(bilibili\.com/video/|b23\.tv/)"
)


def is_bili_url(query: str) -> bool:
    """Return whether a query points to a Bilibili video/short link."""
    return bool(BILI_URL_PATTERN.search(query))


def extract_bili_fav_id(url: str) -> str | None:
    """Extract a Bilibili favorite media_id from supported URLs."""
    match = re.search(r"[?&]fid=(\d+)", url)
    if match:
        return match.group(1)

    match = re.search(r"/medialist/detail/ml(\d+)", url)
    if match:
        return match.group(1)

    match = re.search(r"/list/ml(\d+)", url)
    if match:
        return match.group(1)

    return None


def extract_bili_collection_info(url: str) -> dict | None:
    """Extract Bilibili collection/series identifiers from supported URLs."""
    match = re.search(r"space\.bilibili\.com/(\d+)/lists/(\d+)", url)
    if match:
        mid = match.group(1)
        sid = match.group(2)
        type_match = re.search(r"[?&]type=(\w+)", url)
        list_type = type_match.group(1) if type_match else "season"
        if list_type == "series":
            return {"mid": mid, "series_id": sid}
        return {"mid": mid, "season_id": sid}

    match = re.search(r"bilibili\.com/list/(\d+)\?.*sid=(\d+)", url)
    if match:
        mid = match.group(1)
        sid = match.group(2)
        if "stype=series" in url:
            return {"mid": mid, "series_id": sid}
        return {"mid": mid, "season_id": sid}

    match = re.search(
        r"space\.bilibili\.com/(\d+)/channel/collectiondetail\?sid=(\d+)",
        url,
    )
    if match:
        return {"mid": match.group(1), "season_id": match.group(2)}

    match = re.search(
        r"space\.bilibili\.com/(\d+)/channel/seriesdetail\?sid=(\d+)",
        url,
    )
    if match:
        return {"mid": match.group(1), "series_id": match.group(2)}

    return None


def extract_netease_id(query: str) -> str | None:
    """Extract a NetEase playlist ID from a link or bare numeric ID."""
    query = query.strip()
    if query.isdigit():
        return query

    match = re.search(r"[?&]id=(\d+)", query)
    if match:
        return match.group(1)

    match = re.search(r"/playlist/(\d+)", query)
    if match:
        return match.group(1)

    return None


def clean_search_query(query: str) -> str:
    """Clean noisy music-video titles into a better song search query."""
    if query.strip().startswith(("http://", "https://")):
        return query

    original = query
    parts = []

    song_names = re.findall(r"[《](.+?)[》]", query)
    parts.extend(song_names)

    bracket_noise = {
        "4k", "1080p", "hd", "hi-res", "hires", "mv", "pv",
        "官方", "完整版", "高清", "翻唱", "cover", "原创",
        "自制", "原版", "live", "remix", "ai", "vocaloid",
        "动态歌词", "歌词版", "无损", "hq",
    }
    bracket_contents = re.findall(r"[【\[]([^\]】]+)[】\]]", query)
    for content in bracket_contents:
        content = content.strip()
        if content.lower() not in bracket_noise:
            parts.append(content)

    between = re.findall(r"[】\]]\s*(.+?)\s*[《]", query)
    for text in between:
        text = text.strip()
        if len(text) >= 2 and text.lower() not in bracket_noise:
            parts.append(text)

    if parts:
        seen = set()
        unique = []
        for part in parts:
            if part not in seen:
                seen.add(part)
                unique.append(part)
        return " ".join(unique)

    cleaned = query
    cleaned = re.sub(r"[【\[].*?[】\]]", " ", cleaned)
    cleaned = re.sub(r"[（(].+?[）)]", " ", cleaned)
    for tag in [
        "MV", "PV", "官方", "Official", "4K", "1080P",
        "Hi-res", "Hi-Res", "高清", "完整版", "歌词版",
        "Lyric Video", "无损", "HQ", "HD",
    ]:
        cleaned = cleaned.replace(tag, " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned if len(cleaned) >= 2 else original
