"""Pure helpers for the guess-song game."""
import re


SONG_ALIASES = {
    "晴天": ["晴天", "qingtian"],
    "稻香": ["稻香", "daoxiang"],
    "七里香": ["七里香", "qilixiang"],
    "告白气球": ["告白气球", "gaobaiqiqiu"],
    "青花瓷": ["青花瓷", "qinghuaci"],
    "小幸运": ["小幸运", "xiaoxingyun"],
    "童话": ["童话", "tonghua"],
    "遇见": ["遇见", "yujian"],
    "江南": ["江南", "jiangnan"],
    "演员": ["演员", "yanyuan"],
    "红莲华": ["红莲华", "gurenge"],
    "夜に駆ける": [
        "夜に駆ける",
        "夜奔",
        "yoru ni kakeru",
        "racing into the night",
    ],
    "群青": ["群青", "gunjou"],
    "Lemon": ["lemon", "柠檬"],
}


def calculate_clip_window(
    total_duration: int | float | None,
    requested_duration: int,
) -> tuple[int, int]:
    """Return a safe mid-song start offset and playable clip length."""
    clip_duration = max(1, int(requested_duration))
    try:
        total = max(0, int(total_duration or 0))
    except (TypeError, ValueError):
        total = 0

    if not total:
        return 0, clip_duration

    clip_duration = min(clip_duration, total)
    if total <= clip_duration + 20:
        return 0, clip_duration

    latest_start = max(0, total - clip_duration - 5)
    preferred_start = max(15, int(total * 0.30))
    return min(preferred_start, latest_start), clip_duration


def normalize(text: str) -> str:
    """Normalize text for answer matching."""
    text = text.lower().strip()
    return re.sub(r"[^\w\u4e00-\u9fff]", "", text)


def check_answer(guess: str, song_name: str, artist: str) -> bool:
    """Return whether a guess should count as correct."""
    guess_n = normalize(guess)
    song_n = normalize(song_name)
    artist_n = normalize(artist)

    if guess_n == song_n:
        return True

    if len(song_n) >= 3 and song_n in guess_n:
        return True
    if len(song_n) < 3 and guess_n == song_n:
        return True

    if song_n in guess_n and artist_n in guess_n:
        return True

    aliases = SONG_ALIASES.get(song_name, [])
    return any(normalize(alias) == guess_n for alias in aliases)
