"""Slash command for sharing Black Tibii social networks."""

import discord
from discord import app_commands
from discord.ext import commands


class RedesCog(commands.Cog):
    """Commands that promote Black Tibii social channels."""

    @app_commands.command(
        name="redes",
        description="Muestra las redes sociales de Black Tibii.",
    )
    async def redes(self, interaction: discord.Interaction) -> None:
        """Send the public Black Tibii social media embed."""
        embed = discord.Embed(
            title="🌐 Redes de Black Tibii",
            description="Sígueme en mis redes y acompaña todo el proyecto de Black Tibii. 💀",
            color=discord.Color.dark_red(),
        )
        embed.add_field(
            name="🟦 Facebook",
            value="[facebook.com/the.black.tibii](https://www.facebook.com/the.black.tibii)",
            inline=True,
        )
        embed.add_field(
            name="⬜ Instagram",
            value="[instagram.com/the.black.tibii](https://www.instagram.com/the.black.tibii/)",
            inline=True,
        )
        embed.add_field(
            name="🟥 YouTube",
            value="[youtube.com/@blacktibii](https://www.youtube.com/@blacktibii)",
            inline=True,
        )
        embed.add_field(
            name="🔳 TikTok",
            value="[tiktok.com/@black_tibii](https://www.tiktok.com/@black_tibii)",
            inline=True,
        )
        embed.add_field(
            name="✖️ X (Twitter)",
            value="[x.com/BlackTibii](https://x.com/BlackTibii)",
            inline=True,
        )
        embed.add_field(
            name="🧵 Threads",
            value="[threads.com/@the.black.tibii](https://www.threads.com/@the.black.tibii)",
            inline=True,
        )
        embed.add_field(
            name="💭 Discord",
            value="https://discord.gg/Zz6Xp7TfDa",
            inline=True,
        )
        embed.add_field(
            name="🟩 Canal de WhatsApp",
            value=(
                "[whatsapp.com/channel/0029Vab4ZUt6xCSQVSXKo60G]"
                "(https://www.whatsapp.com/channel/0029Vab4ZUt6xCSQVSXKo60G)"
            ),
            inline=True,
        )
        embed.set_footer(text="Black Tibii • Conecta con la comunidad")

        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    """Register this command module with Odinus."""
    await bot.add_cog(RedesCog())
