"""Cookie-file helpers for Bilibili requests."""
from pathlib import Path
from tempfile import NamedTemporaryFile
import os


def parse_netscape_cookie_file(path: str | Path) -> dict[str, str]:
    """Parse a Netscape cookies.txt file into a requests-compatible dict."""
    cookies: dict[str, str] = {}
    cookie_path = Path(path)
    if not cookie_path.exists():
        return cookies

    with cookie_path.open("r", encoding="utf-8") as file:
        for raw_line in file:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                cookies[parts[5]] = parts[6]

    return cookies


def parse_netscape_cookie_text(text: str) -> dict[str, str]:
    """Parse Netscape cookies.txt content into a dict."""
    cookies: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7:
            cookies[parts[5]] = parts[6]
    return cookies


def validate_bili_cookie_text(text: str) -> dict[str, str]:
    """Validate that uploaded cookies look useful for Bilibili."""
    cookies = parse_netscape_cookie_text(text)
    required = {"SESSDATA"}
    missing = sorted(required - set(cookies))
    if missing:
        raise ValueError(f"cookies 缺少关键字段: {', '.join(missing)}")
    return cookies


def replace_cookie_file(path: str | Path, content: bytes) -> bool:
    """Delete the old cookie file and atomically write the new one."""
    cookie_path = Path(path)
    cookie_path.parent.mkdir(parents=True, exist_ok=True)
    had_old_file = cookie_path.exists()
    if had_old_file:
        cookie_path.unlink()

    with NamedTemporaryFile(
        "wb",
        delete=False,
        dir=str(cookie_path.parent),
        prefix=f".{cookie_path.name}.",
        suffix=".tmp",
    ) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    os.replace(tmp_path, cookie_path)
    return had_old_file
