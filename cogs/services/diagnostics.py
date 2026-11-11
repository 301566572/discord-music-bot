"""Runtime diagnostics for deployment and support commands."""
import os
import shutil
import sys
from importlib.metadata import PackageNotFoundError, version


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

    try:
        installed = version("discord.py")
        numbers = tuple(int(part) for part in installed.split(".")[:3])
        checks.append(("discord.py", numbers >= (2, 7, 1), installed + "（需要 2.7.1+）"))
    except (PackageNotFoundError, ValueError):
        checks.append(("discord.py", False, "无法确认版本，请更新依赖"))
    try:
        import davey  # noqa: F401
    except Exception:
        checks.append(("DAVE 语音加密", False, "不可用，请更新 discord.py[voice]"))
    else:
        checks.append(("DAVE 语音加密", True, "可用"))

    return checks


def voice_checks(vc, player=None) -> list[tuple[str, bool, str]]:
    """Describe observable voice state without exposing stream URLs or credentials."""
    if vc is None or not vc.is_connected():
        return [("语音连接", False, "未连接语音频道")]
    checks = [("语音连接", True, "已连接")]
    playing, paused = vc.is_playing(), vc.is_paused()
    checks.append(("音频发送线程", playing, "运行中（不代表听众已收到声音）" if playing else "已暂停" if paused else "未运行"))
    if player is not None:
        checks.append(("播放器音量", player.volume > 0, f"{round(player.volume * 100)}%"))
    me = vc.guild.me
    state = me.voice if me else None
    if state:
        blocked = state.mute or state.suppress
        checks.append(("服务器语音状态", not blocked, "已被禁言或被抑制发言" if blocked else "未被服务器禁言"))
    if me and vc.channel:
        allowed = vc.channel.permissions_for(me).speak
        checks.append(("频道发言权限", allowed, "允许" if allowed else "不允许"))
    return checks


def format_checks(checks: list[tuple[str, bool, str]]) -> str:
    """Format diagnostic checks for Discord output."""
    lines = []
    for name, ok, detail in checks:
        mark = "OK" if ok else "FAIL"
        lines.append(f"`{mark}` **{name}**: {detail}")
    return "\n".join(lines)
