import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True  # needed for on_message
intents.reactions = True
intents.members = True

bot = commands.Bot(command_prefix=None, intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (id: {bot.user.id})")

    try:
        synced = await bot.tree.sync()
        print(f"🔧 Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"❌ Slash sync failed: {e}")

async def main():
    if not TOKEN:
        raise RuntimeError("❌ DISCORD_TOKEN is missing in .env")

    async with bot:
        # load your cogs here
        await bot.load_extension("cogs.general")
        # await bot.load_extension("cogs.messages")
        await bot.load_extension("cogs.reactions")
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
