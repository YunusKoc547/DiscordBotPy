import discord
from discord.ext import commands

class MessageCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # example listener
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author == self.bot.user:
            return
        
        target_roles = [776328568036392972, 1282865161945874543, 1416872124236431490]  
        for role in message.role_mentions:
            if any(role.id in target_roles for role in message.role_mentions):
                print("entered")
                await message.add_reaction("✅")
            


async def setup(bot: commands.Bot):
    await bot.add_cog(MessageCog(bot))
