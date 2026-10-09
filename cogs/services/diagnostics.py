"""Runtime diagnostics for deployment and support commands."""
import os
import shutil
import sys


def check_runtime_environment() -> list[tuple[str, bool, str]]:
    """Return deploy-time checks as (name, ok, detail)."""
    ffmpeg_path = shutil.which("ffmpeg")
    token_present = bool(os.getenv("DISCORD_TOKEN"))

    checks = [
        (
            "DISCORD_TOKEN",
            token_present,
            "已设置" if token_present else "未设置，请检查 .env",
        ),
        (
            "FFmpeg",
            bool(ffmpeg_path),
            ffmpeg_path or "未在 PATH 中找到",
        ),
        (
            "Python",
            True,
            sys.version.split()[0],
        ),
    ]

    try:
        import nacl  # noqa: F401
    except Exception as exc:
        checks.append(("PyNaCl", False, f"不可用: {exc}"))
    else:
        checks.append(("PyNaCl", True, "可用"))

    return checks


def format_checks(checks: list[tuple[str, bool, str]]) -> str:
    """Format diagnostic checks for Discord output."""
    lines = []
    for name, ok, detail in checks:
        mark = "OK" if ok else "FAIL"
        lines.append(f"`{mark}` **{name}**: {detail}")
    return "\n".join(lines)
