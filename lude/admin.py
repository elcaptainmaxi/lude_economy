import json
import math
import sqlite3
import time
from typing import Optional

import discord
from discord import app_commands

from . import config
from .groups import admin_group
from .views import LudeAdminConfirmation, LudeAdminPanel


class AdminMixin:
    def load_runtime_settings(self):
        with self.db_lock:
            conn = self.connect()
            rows = conn.execute("SELECT key, value FROM economy_settings").fetchall()
            conn.close()
        for row in rows:
            spec = config.SETTING_SPECS.get(row["key"])
            if not spec:
                continue
            try:
                config.apply_setting_value(spec, json.loads(row["value"]))
            except Exception as exc:
                print(f"[LudeEconomy] Ajuste inválido ignorado {row['key']}: {exc}")

    def update_runtime_setting(self, key: str, value, updated_by: int, restore: bool = False):
        spec = config.SETTING_SPECS.get(key)
        if not spec:
            raise KeyError("Ajuste inexistente")
        previous_value = config.setting_display_value(spec)
        parsed = config.apply_setting_value(spec, value)

        try:
            if key.endswith("salary_min"):
                job_id = key.split(".")[1]
                if config.JOBS[job_id]["salary"][0] > config.JOBS[job_id]["salary"][1]:
                    raise ValueError("El salario mínimo no puede superar al salario máximo.")
            elif key.endswith("salary_max"):
                job_id = key.split(".")[1]
                if config.JOBS[job_id]["salary"][1] < config.JOBS[job_id]["salary"][0]:
                    raise ValueError("El salario máximo no puede ser menor al salario mínimo.")
            elif key.endswith("auto_min_pct"):
                symbol = key.split(".")[1]
                if config.CRYPTO_CONFIG[symbol]["auto_min"] > config.CRYPTO_CONFIG[symbol]["auto_max"]:
                    raise ValueError("La volatilidad mínima no puede superar la máxima.")
            elif key.endswith("auto_max_pct"):
                symbol = key.split(".")[1]
                if config.CRYPTO_CONFIG[symbol]["auto_max"] < config.CRYPTO_CONFIG[symbol]["auto_min"]:
                    raise ValueError("La volatilidad máxima no puede ser menor a la mínima.")
            elif key in {"rob.theft_min_pct", "rob.theft_max_pct"}:
                if config.ROB_THEFT_MIN_PERCENT > config.ROB_THEFT_MAX_PERCENT:
                    raise ValueError("El porcentaje mínimo de robo no puede superar al máximo.")
            elif key.startswith("crime.") and key.endswith(".weight"):
                if sum(max(0, float(item["weight"])) for item in config.CRIME_CATEGORIES.values()) <= 0:
                    raise ValueError("Al menos una categoría de crimen debe tener peso mayor que 0.")
            elif key.startswith("casino.slots.weight."):
                if sum(max(0, float(weight)) for weight in config.SLOTS_SYMBOL_WEIGHTS.values()) <= 0:
                    raise ValueError("Al menos un símbolo de Slots debe tener peso mayor que 0.")
        except ValueError:
            config.apply_setting_value(spec, previous_value)
            raise

        with self.db_lock:
            conn = self.connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                if restore:
                    conn.execute("DELETE FROM economy_settings WHERE key = ?", (key,))
                else:
                    conn.execute(
                        """INSERT INTO economy_settings(key, value, updated_by, updated_at)
                           VALUES(?, ?, ?, ?) ON CONFLICT(key) DO UPDATE SET
                           value = excluded.value, updated_by = excluded.updated_by,
                           updated_at = excluded.updated_at""",
                        (key, json.dumps(parsed, ensure_ascii=False), updated_by, int(time.time())),
                    )
                conn.execute(
                    """INSERT INTO economy_admin_audit
                       (setting_key, action, previous_value, new_value, changed_by, changed_at)
                       VALUES(?, ?, ?, ?, ?, ?)""",
                    (key, "restaurar" if restore else "cambiar",
                     json.dumps(previous_value, ensure_ascii=False),
                     json.dumps(parsed, ensure_ascii=False), updated_by, int(time.time())),
                )
                if key.startswith("crypto.") and key.endswith(".fundamental"):
                    symbol = key.split(".")[1]
                    conn.execute(
                        "UPDATE crypto_engine_state SET fundamental = ?, stable_ticks = 0 WHERE symbol = ?",
                        (float(parsed), symbol),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                config.apply_setting_value(spec, previous_value)
                raise
            finally:
                conn.close()
        return parsed

    def reset_runtime_setting(self, key: str, updated_by: int):
        spec = config.SETTING_SPECS.get(key)
        if not spec:
            raise KeyError("Ajuste inexistente")
        return self.update_runtime_setting(key, spec.default, updated_by, restore=True)

    def member_is_admin(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == config.ADMIN_OWNER_ID

    async def require_admin(self, interaction: discord.Interaction) -> bool:
        if self.member_is_admin(interaction):
            return True
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "⛔ Solo el dueño del bot puede utilizar este comando.", ephemeral=True
            )
        return False

    def build_admin_history_embed(self) -> discord.Embed:
        with self.db_lock:
            conn = self.connect()
            try:
                rows = conn.execute(
                    """SELECT setting_key, action, previous_value, new_value, changed_by, changed_at
                       FROM economy_admin_audit ORDER BY id DESC LIMIT 10"""
                ).fetchall()
            finally:
                conn.close()
        embed = discord.Embed(title="📋 Lude Admin · Últimos cambios", color=config.COLOR)
        if not rows:
            embed.description = "Todavía no hay cambios registrados. Los cambios anteriores a esta actualización no se reconstruyen."
        else:
            lines = []
            for row in rows:
                before = config.format_setting_value(json.loads(row["previous_value"]))
                after = config.format_setting_value(json.loads(row["new_value"]))
                icon = "♻️" if row["action"] == "restaurar" else "✏️"
                lines.append(
                    f"**{icon} `{row['setting_key']}`**: {before} → {after} · "
                    f"<@{row['changed_by']}> · <t:{row['changed_at']}:R>"
                )
            embed.description = "\n".join(lines)[:4000]
        return embed

    @admin_group.command(name="listar", description="Lista los ajustes modificables de la economía.")
    async def admin_listar(self, interaction: discord.Interaction, categoria: Optional[str] = None, pagina: int = 1):
        if not await self.require_admin(interaction):
            return
        category = categoria.lower().strip() if categoria else None
        if category and category not in config.SETTING_CATEGORIES:
            await interaction.response.send_message(
                f"Categoría inválida. Usa: **{', '.join(config.SETTING_CATEGORIES)}**.", ephemeral=False
            )
            return
        items = [item for item in config.SETTING_SPECS.values() if category is None or item.category == category]
        items.sort(key=lambda spec: spec.key)
        per_page = 15
        pages = max(1, math.ceil(len(items) / per_page))
        page = max(1, min(int(pagina), pages))
        lines = []
        for spec in items[(page - 1) * per_page:page * per_page]:
            current = config.setting_display_value(spec)
            marker = "" if current == spec.default else " ✏️"
            lines.append(f"`{spec.key}` = **{config.format_setting_value(current)}**{marker}")
        embed = discord.Embed(
            title="⚙️ Lude Admin · Configuración",
            description="\n".join(lines) if lines else "No hay ajustes en esta categoría.",
            color=config.COLOR,
        )
        embed.set_footer(text=f"Página {page}/{pages} · {len(items)} ajustes · ✏️ = modificado")
        await interaction.response.send_message(embed=embed, ephemeral=False)

    @admin_listar.autocomplete("categoria")
    async def admin_categoria_autocomplete(self, interaction: discord.Interaction, current: str):
        if not self.member_is_admin(interaction):
            return []
        current = current.lower()
        return [app_commands.Choice(name=item, value=item) for item in config.SETTING_CATEGORIES if current in item][:25]

    @admin_group.command(name="ver", description="Muestra un ajuste, su valor actual y el predeterminado.")
    async def admin_ver(self, interaction: discord.Interaction, clave: str):
        if not await self.require_admin(interaction):
            return
        spec = config.SETTING_SPECS.get(clave)
        if not spec:
            await interaction.response.send_message("Ajuste inexistente.", ephemeral=False)
            return
        current = config.setting_display_value(spec)
        embed = discord.Embed(title="⚙️ Ajuste de Lude", color=config.COLOR)
        embed.add_field(name="Clave", value=f"`{spec.key}`", inline=False)
        embed.add_field(name="Descripción", value=spec.label, inline=False)
        embed.add_field(name="Actual", value=f"**{config.format_setting_value(current)}**", inline=True)
        embed.add_field(name="Predeterminado", value=f"**{config.format_setting_value(spec.default)}**", inline=True)
        embed.add_field(name="Categoría", value=spec.category, inline=True)
        restrictions = []
        if spec.minimum is not None:
            restrictions.append(f"mín {spec.minimum}")
        if spec.maximum is not None:
            restrictions.append(f"máx {spec.maximum}")
        if spec.choices:
            restrictions.append(" / ".join(spec.choices))
        if restrictions:
            embed.add_field(name="Límites", value=" · ".join(restrictions), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=False)

    @admin_group.command(name="cambiar", description="Propone un cambio; requiere confirmación.")
    async def admin_cambiar(self, interaction: discord.Interaction, clave: str, valor: str):
        if not await self.require_admin(interaction):
            return
        spec = config.SETTING_SPECS.get(clave)
        if not spec:
            await interaction.response.send_message("Ajuste inexistente.")
            return
        try:
            parsed = config.parse_setting_value(spec, valor)
        except ValueError as exc:
            await interaction.response.send_message(f"❌ {exc}")
            return
        view = LudeAdminConfirmation(self, interaction.user.id, clave, parsed)
        await interaction.response.send_message(embed=view.render(), view=view)
        view.message = await interaction.original_response()

    @admin_group.command(name="restaurar", description="Propone restaurar el valor predeterminado; requiere confirmación.")
    async def admin_restaurar(self, interaction: discord.Interaction, clave: str):
        if not await self.require_admin(interaction):
            return
        spec = config.SETTING_SPECS.get(clave)
        if not spec:
            await interaction.response.send_message("Ajuste inexistente.")
            return
        view = LudeAdminConfirmation(self, interaction.user.id, clave, spec.default, restore=True)
        await interaction.response.send_message(embed=view.render(), view=view)
        view.message = await interaction.original_response()

    @admin_group.command(name="panel", description="Abre el panel administrativo interactivo.")
    async def admin_panel(self, interaction: discord.Interaction):
        if not await self.require_admin(interaction):
            return
        view = LudeAdminPanel(self, interaction.user.id)
        await interaction.response.send_message(embed=view.render(), view=view)
        view.message = await interaction.original_response()

    @admin_group.command(name="historial", description="Consulta los últimos diez cambios administrativos.")
    async def admin_historial(self, interaction: discord.Interaction):
        if not await self.require_admin(interaction):
            return
        await interaction.response.send_message(embed=self.build_admin_history_embed())

    def _admin_key_choices(self, interaction: discord.Interaction, current: str):
        if not self.member_is_admin(interaction):
            return []
        current = current.lower().strip()
        matches = [
            spec for spec in config.SETTING_SPECS.values()
            if current in spec.key.lower() or current in spec.label.lower()
        ]
        matches.sort(key=lambda spec: (not spec.key.lower().startswith(current), spec.key))
        return [app_commands.Choice(name=spec.key[:100], value=spec.key) for spec in matches[:25]]

    @admin_ver.autocomplete("clave")
    async def admin_ver_key_autocomplete(self, interaction: discord.Interaction, current: str):
        return self._admin_key_choices(interaction, current)

    @admin_cambiar.autocomplete("clave")
    async def admin_cambiar_key_autocomplete(self, interaction: discord.Interaction, current: str):
        return self._admin_key_choices(interaction, current)

    @admin_restaurar.autocomplete("clave")
    async def admin_restaurar_key_autocomplete(self, interaction: discord.Interaction, current: str):
        return self._admin_key_choices(interaction, current)
