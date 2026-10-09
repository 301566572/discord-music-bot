"""Discord commands for runtime diagnostics."""
import discord
from discord.ext import commands

from cogs.services.diagnostics import check_runtime_environment, format_checks


class Diagnostics(commands.Cog, name="🛠️ 诊断"):
    """Deployment and runtime support commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(
        name="诊断",
        aliases=["diagnose", "health", "状态检查"],
        help="检查机器人运行环境和已加载模块",
    )
    async def diagnose(self, ctx: commands.Context):
        checks = check_runtime_environment()
        loaded = sorted(self.bot.extensions.keys())
        latency_ms = round(self.bot.latency * 1000)

        description = (
            f"{format_checks(checks)}\n\n"
            f"**Discord 延迟**: `{latency_ms} ms`\n"
            f"**已加载模块**: `{', '.join(loaded) or '无'}`"
        )
        embed = discord.Embed(
            title="运行诊断",
            description=description,
            color=discord.Color.green()
            if all(ok for _, ok, _ in checks)
            else discord.Color.orange(),
        )
        await ctx.send(embed=embed, silent=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Diagnostics(bot))
