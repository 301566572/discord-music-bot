"""Pure title-cleaning helpers for lyrics search."""
import re


COVER_INDICATORS = [
    "AI", "ai", "翻唱", "cover", "Cover", "COVER",
    "东雪莲", "洛天依", "初音", "ミク", "VOCALOID",
    "remix", "Remix", "改编", "自制",
]


def is_cover_artist(name: str) -> bool:
    return any(tag in name for tag in COVER_INDICATORS)


def extract_lyrics_candidates(title: str) -> list[str]:
    """Extract likely song-title search candidates from a video title."""
    candidates = []
    song_in_brackets = None
    artist_maybe = None

    bracket_match = re.search(
        r"[【\[]([^\]】]+)[】\]]\s*[《](.+?)[》]", title
    )
    plain_match = re.search(
        r"([\u4e00-\u9fff\w]{2,8})\s*[《](.+?)[》]", title
    )
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
        if artist_maybe and is_cover_artist(artist_maybe):
            candidates.append(song_in_brackets)
            candidates.append(f"{song_in_brackets} 原唱")
        elif artist_maybe:
            candidates.append(f"{artist_maybe} {song_in_brackets}")

        if song_in_brackets not in candidates:
            candidates.append(song_in_brackets)

        if artist_maybe and "·" in song_in_brackets:
            cleaned = song_in_brackets.replace("·", " ")
            if not is_cover_artist(artist_maybe):
                candidates.append(f"{artist_maybe} {cleaned}")
            candidates.append(cleaned)

    cleaned_title = title
    cleaned_title = re.sub(r"[【\[].*?[】\]]", " ", cleaned_title)
    cleaned_title = re.sub(r"[《](.+?)[》]", r" \1 ", cleaned_title)
    cleaned_title = re.sub(r"[「](.+?)[」]", r" \1 ", cleaned_title)
    cleaned_title = re.sub(
        r"\((?:官方|official|MV|lyric|歌词|live|翻唱|cover|"
        r"feat\.?|完整版|高清|HD|4K|1080p|视频|audio|"
        r"动态歌词|字幕|中文|日文|英文|高音质)[^)]*\)",
        " ",
        cleaned_title,
        flags=re.IGNORECASE,
    )
    cleaned_title = re.sub(r"\([^)]{10,}\)", " ", cleaned_title)
    for tag in [
        "MV", "PV", "官方", "Official", "Lyric Video",
        "歌词版", "完整版", "高清", "4K", "1080P", "Hi-res",
        "翻唱", "Cover", "cover", "Live", "live",
        "动态歌词", "无损", "HQ", "HD", "Hi-Res", "hi-res",
    ]:
        cleaned_title = cleaned_title.replace(tag, " ")
    cleaned_title = re.sub(r"[｜|／/\\～~—–_]", " ", cleaned_title)
    cleaned_title = cleaned_title.replace(" - ", " ").replace("-", " ")
    cleaned_title = re.sub(r"\s+", " ", cleaned_title).strip()

    if len(cleaned_title) >= 2 and cleaned_title not in candidates:
        candidates.append(cleaned_title)

    dash_match = re.match(r"^(.+?)\s*[-–—]\s*(.+?)(?:\s|$)", title)
    if dash_match:
        part1 = dash_match.group(1).strip()
        part2 = dash_match.group(2).strip()
        combo = f"{part1} {part2}"
        if combo not in candidates:
            candidates.append(combo)

    if cleaned_title and " " in cleaned_title:
        parts = cleaned_title.split()
        cn_parts = [
            part for part in parts
            if len(part) >= 2 and re.search(r"[\u4e00-\u9fff]", part)
        ]
        if cn_parts:
            shortest = min(cn_parts, key=len)
            if shortest not in candidates:
                candidates.append(shortest)

    seen = set()
    unique = []
    for candidate in candidates:
        candidate = candidate.strip()
        if candidate and candidate not in seen:
            seen.add(candidate)
            unique.append(candidate)

    return unique or [title.strip()]
