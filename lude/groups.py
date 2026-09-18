import discord
from discord import app_commands

from . import config


class TesterLudeGroup(app_commands.Group):
    async def interaction_check(self, interaction: discord.Interaction, /) -> bool:
        if interaction.guild_id != config.GUILD_ID:
            return False

        member = interaction.user
        tester_role = interaction.guild.get_role(config.TESTER_ROLE_ID) if interaction.guild else None
        allowed = (
            isinstance(member, discord.Member)
            and (
                member.guild_permissions.administrator
                or (tester_role is not None and member.top_role.position >= tester_role.position)
            )
        )
        if allowed:
            return True

        if interaction.type != discord.InteractionType.autocomplete and not interaction.response.is_done():
            await interaction.response.send_message(
                f"🧪 Este sistema está en **testing**. Necesitas el rol <@&{config.TESTER_ROLE_ID}> para usar `/lude`.",
                ephemeral=True,
            )
        return False


class OwnerAdminGroup(app_commands.Group):
    """Defensa adicional: todo el subgrupo exige el owner configurado."""

    async def interaction_check(self, interaction: discord.Interaction, /) -> bool:
        if interaction.user.id == config.ADMIN_OWNER_ID:
            return True
        if interaction.type != discord.InteractionType.autocomplete and not interaction.response.is_done():
            await interaction.response.send_message(
                "⛔ Solo el dueño del bot puede utilizar `/lude admin`.", ephemeral=True
            )
        return False


lude = TesterLudeGroup(
    name="lude",
    description="Economía de Interlude (testing).",
    guild_ids=[config.GUILD_ID],
    guild_only=True,
)
crypto_group = app_commands.Group(
    name="crypto",
    description="Mercado e inversiones en criptomonedas.",
    parent=lude,
)
admin_group = OwnerAdminGroup(
    name="admin",
    description="Configuración administrativa de la economía.",
    parent=lude,
)
