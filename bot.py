import discord
from discord import app_commands, ui
from discord.ext import commands
import sqlite3
from datetime import datetime
import asyncio
import os
import traceback
from dotenv import load_dotenv

load_dotenv()

# ========================= НАСТРОЙКИ =========================
TOKEN = os.getenv("TOKEN")

CLAN_NAME = "Falcon's - Dogs"
ROLE_ID = 1374753135553413202              # ← Замени
LOG_CHANNEL_ID = 1408467918647197726       # ← Замени
GUILD_ID = 1158465046612029490             # ← ID твоего сервера
OWNER_ID = 842068301459095563             # ← ТВОЙ Discord ID (для команды /sync)

# ============================================================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# ====================== БАЗА ДАННЫХ ======================
conn = sqlite3.connect("war_stats.db", check_same_thread=False)
cur = conn.cursor()
cur.execute("""CREATE TABLE IF NOT EXISTS stats (id INTEGER PRIMARY KEY, w INTEGER, d INTEGER, l INTEGER)""")
cur.execute("INSERT OR IGNORE INTO stats (id, w, d, l) VALUES (1, 0, 0, 0)")
conn.commit()


def get_stats():
    cur.execute("SELECT w, d, l FROM stats WHERE id=1")
    return cur.fetchone() or (0, 0, 0)


def update_stats(result: str):
    w, d, l = get_stats()
    if result == "W": w += 1
    elif result == "L": l += 1
    elif result == "D": d += 1
    cur.execute("UPDATE stats SET w=?, d=?, l=? WHERE id=1", (w, d, l))
    conn.commit()
    return w, d, l


# ========================= VIEW =========================
class WarConfirmView(ui.View):
    def __init__(self, embed_data: dict, user_id: int, channel_id: int):
        super().__init__(timeout=300)
        self.embed_data = embed_data
        self.user_id = user_id
        self.channel_id = channel_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Это не твоя анкета.", ephemeral=True)
            return False
        return True

    @ui.button(label="✅ Подтвердить", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(content="⏳ Обрабатываю...", embed=None, view=None)

        channel = bot.get_channel(self.channel_id)
        instruction_msg = None

        try:
            instruction_msg = await channel.send(
                f"{interaction.user.mention} Прикрепи скриншоты в следующем сообщении.\n"
                f"Если скриншотов нет — напиши `готово`."
            )

            def check(m: discord.Message):
                return m.author.id == self.user_id and m.channel.id == self.channel_id

            msg = await bot.wait_for('message', check=check, timeout=300.0)

            files = [await att.to_file() for att in msg.attachments] if msg.attachments else []

            w, d, l = update_stats(self.embed_data["result"])

            embed = discord.Embed(
                title="⚔️ Лог войны",
                color=0xFFFFFF,
                timestamp=datetime.now()
            )
            embed.description = self.embed_data["title"]
            embed.add_field(name="Результат", value=f"**{self.embed_data['result']}**", inline=True)
            embed.add_field(name="Счётчик", value=f"`{w} {d} {l}`", inline=True)        # Только цифры
            embed.add_field(name="Дата", value=f"<t:{int(datetime.now().timestamp())}:D>", inline=False)

            if self.embed_data.get("extra"):
                embed.add_field(name="Дополнительно", value=self.embed_data["extra"] or "—", inline=False)
            if self.embed_data["proof"].strip() not in ["-", "—", ""]:
                embed.add_field(name="Ссылки на доказательства", value=self.embed_data["proof"], inline=False)

            embed.set_footer(text=f"Записал: {interaction.user.display_name}")

            log_channel = bot.get_channel(LOG_CHANNEL_ID)
            if log_channel:
                await log_channel.send(embed=embed)
                if files:
                    await log_channel.send(files=files)          # Скриншоты снизу

            if instruction_msg: 
                await instruction_msg.delete()
            await msg.delete()

            try:
                await interaction.user.send(embed=discord.Embed(
                    title="✅ Лог успешно записан",
                    description="**Слава Falcon's - Dogs!** 🔥",
                    color=0xFFFFFF
                ))
            except:
                pass

        except asyncio.TimeoutError:
            if instruction_msg:
                await instruction_msg.edit(content="⏰ Время вышло.")
        except Exception:
            traceback.print_exc()
            if instruction_msg:
                await instruction_msg.delete()


# ========================= МОДАЛЬНОЕ ОКНО =========================
class WarLogModal(ui.Modal, title="📋 Лог войны"):
    enemy = ui.TextInput(label="1. Против какого клана(-ов)?", placeholder="ATR, Astrals, CVA...", required=True)
    allies = ui.TextInput(label="2. Союзники (или '-')", placeholder="Напиши '-' если не было", required=True)
    result = ui.TextInput(label="3. Результат (W / D / L)", placeholder="W, D или L", max_length=1, required=True)
    extra_info = ui.TextInput(label="4. Дополнительная информация", 
                              placeholder="Длительность, auto-win...", 
                              style=discord.TextStyle.paragraph, required=False)
    proof = ui.TextInput(label="5. Ссылки на доказательства", 
                         placeholder="Google диск, YouTube... Или '-'", 
                         style=discord.TextStyle.paragraph, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        result = self.result.value.strip().upper()
        if result not in ["W", "L", "D"]:
            return await interaction.response.send_message("❌ Результат может быть только **W**, **D** или **L**!", ephemeral=True)

        allies = self.allies.value.strip()
        title = f"**{CLAN_NAME} vs {self.enemy.value.strip()}**" if allies.lower() in ["-", "—", "нет", ""] else \
                f"**{CLAN_NAME} + {allies} vs {self.enemy.value.strip()}**"

        embed_data = {
            "title": title,
            "result": result,
            "extra": self.extra_info.value.strip(),
            "proof": self.proof.value.strip()
        }

        view = WarConfirmView(embed_data, interaction.user.id, interaction.channel_id)
        
        preview = discord.Embed(title="Предпросмотр лога", color=0xFFFFFF, description=title)
        preview.add_field(name="Результат", value=result, inline=True)
        preview.add_field(name="Счётчик", value="—", inline=True)
        preview.add_field(name="Дополнительно", value=embed_data["extra"] or "—", inline=False)
        preview.add_field(name="Ссылки", value=embed_data["proof"] if embed_data["proof"].strip() not in ["-", "—", ""] else "—", inline=False)

        await interaction.response.send_message(embed=preview, view=view, ephemeral=True)


# ====================== КОМАНДЫ ======================
@tree.command(name="logwar", description="Создать лог войны")
@app_commands.checks.has_role(ROLE_ID)
async def logwar(interaction: discord.Interaction):
    await interaction.response.send_modal(WarLogModal())


@tree.command(name="warstats", description="Показать статистику войн")
async def warstats(interaction: discord.Interaction):
    w, d, l = get_stats()
    total = w + d + l
    winrate = round((w / total * 100), 1) if total > 0 else 0.0

    embed = discord.Embed(
        title="📊 Статистика Falcon's - Dogs",
        color=0xFFFFFF,
        timestamp=datetime.now()
    )
    embed.add_field(name="Всего войн", value=f"`{total}`", inline=False)
    embed.add_field(name="Победы", value=f"**{w}** 🟢", inline=True)
    embed.add_field(name="Ничьи", value=f"**{d}** ⚪", inline=True)
    embed.add_field(name="Поражения", value=f"**{l}** 🔴", inline=True)
    embed.add_field(name="Winrate", value=f"`{winrate}%`", inline=False)
    embed.set_footer(text="Falcon's - Dogs • Статистика обновляется в реальном времени")

    await interaction.response.send_message(embed=embed)


@tree.command(name="sync", description="Принудительно обновить слэш-команды")
@app_commands.checks.has_permissions(administrator=True)
async def sync_commands(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        return await interaction.response.send_message("❌ Только владелец может использовать эту команду.", ephemeral=True)
    
    await interaction.response.defer(ephemeral=True)
    try:
        await tree.sync()
        await tree.sync(guild=discord.Object(id=GUILD_ID))
        await interaction.followup.send("✅ Команды успешно синхронизированы!\nТеперь попробуй написать `/warstats`", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Ошибка синхронизации:\n`{e}`", ephemeral=True)


# ====================== ЗАПУСК ======================
@bot.event
async def on_ready():
    print(f"✅ {bot.user} успешно запущен!")
    try:
        await tree.sync(guild=discord.Object(id=GUILD_ID))
        await tree.sync()
        print("Команды синхронизированы.")
    except Exception as e:
        print("Ошибка автосинхронизации:", e)


bot.run(TOKEN)
