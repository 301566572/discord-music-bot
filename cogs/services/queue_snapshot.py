"""Queue import/export helpers."""
import json
import re
from pathlib import Path


SNAPSHOT_VERSION = 1
QUEUE_STORE_DIR = Path(__file__).resolve().parents[2] / "data" / "queues"


def empty_snapshot() -> dict:
    """Return a valid empty named-playlist payload."""
    return {
        "version": SNAPSHOT_VERSION,
        "volume": 0.5,
        "loop": False,
        "loop_queue": False,
        "audio_filter": None,
        "current": None,
        "queue": [],
    }


def song_to_record(song) -> dict:
    """Convert a Song-like object into a JSON-serializable record."""
    return {
        "source_url": song.source_url,
        "title": song.title,
        "webpage_url": song.webpage_url,
        "duration": song.duration,
        "thumbnail": song.thumbnail,
        "is_bili": song.is_bili,
        "search_query": song.search_query,
    }


def build_snapshot(player) -> dict:
    """Build an export payload from a MusicPlayer-like object."""
    return {
        "version": SNAPSHOT_VERSION,
        "volume": player.volume,
        "loop": player.loop,
        "loop_queue": player.loop_queue,
        "audio_filter": player.audio_filter,
        "current": song_to_record(player.current) if player.current else None,
        "queue": [song_to_record(song) for song in player.queue],
    }


def validate_snapshot(payload: dict) -> list[dict]:
    """Validate and return queue records from an imported payload."""
    if not isinstance(payload, dict):
        raise ValueError("队列文件格式错误")
    if payload.get("version") != SNAPSHOT_VERSION:
        raise ValueError("队列文件版本不兼容")
    records = payload.get("queue", [])
    if not isinstance(records, list):
        raise ValueError("队列内容格式错误")
    for record in records:
        if not isinstance(record, dict) or not record.get("title"):
            raise ValueError("队列中存在无效歌曲")
    return records


def records_from_snapshot(
    payload: dict, *, include_current: bool = False
) -> list[dict]:
    """Validate a snapshot and return playable records."""
    records = validate_snapshot(payload)
    if include_current and isinstance(payload.get("current"), dict):
        current = payload["current"]
        if current.get("title"):
            return [current, *records]
    return records


def sanitize_queue_name(name: str) -> str:
    """Convert a user-provided queue name into a safe file stem."""
    cleaned = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", name.strip())
    cleaned = cleaned.strip("._")
    if not cleaned:
        raise ValueError("队列名称不能为空")
    if len(cleaned) > 64:
        cleaned = cleaned[:64].rstrip("._")
    return cleaned


def guild_queue_dir(guild_id: int | str) -> Path:
    path = QUEUE_STORE_DIR / str(guild_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def queue_file_path(guild_id: int | str, name: str) -> Path:
    return guild_queue_dir(guild_id) / f"{sanitize_queue_name(name)}.json"


def save_named_queue(guild_id: int | str, name: str, payload: dict) -> Path:
    """Save a queue snapshot under a guild-local name."""
    records_from_snapshot(payload, include_current=True)
    path = queue_file_path(guild_id, name)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def create_named_queue(guild_id: int | str, name: str) -> Path:
    """Create an empty guild-local playlist without overwriting one."""
    path = queue_file_path(guild_id, name)
    if path.exists():
        raise FileExistsError(f"歌单 `{path.stem}` 已存在")
    return save_named_queue(guild_id, name, empty_snapshot())


def append_named_queue_record(
    guild_id: int | str, name: str, record: dict
) -> tuple[Path, int]:
    """Append one validated song record and return path and new size."""
    payload = load_named_queue(guild_id, name)
    validate_snapshot({**payload, "queue": [record]})
    payload.setdefault("queue", []).append(record)
    path = save_named_queue(guild_id, name, payload)
    return path, len(payload["queue"])


def load_named_queue(guild_id: int | str, name: str) -> dict:
    path = queue_file_path(guild_id, name)
    if not path.exists():
        raise FileNotFoundError(f"找不到名为 `{sanitize_queue_name(name)}` 的队列")
    return json.loads(path.read_text(encoding="utf-8"))


def list_named_queues(guild_id: int | str) -> list[str]:
    path = guild_queue_dir(guild_id)
    return sorted(item.stem for item in path.glob("*.json") if item.is_file())


def delete_named_queue(guild_id: int | str, name: str) -> str:
    safe_name = sanitize_queue_name(name)
    path = queue_file_path(guild_id, safe_name)
    if not path.exists():
        raise FileNotFoundError(f"找不到名为 `{safe_name}` 的队列")
    path.unlink()
    return safe_name
