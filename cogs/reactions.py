# cogs/reactions.py
import discord
from discord.ext import commands

class ReactionCog(commands.Cog):
    """
    - Adds a ✅ reaction when certain roles are mentioned.
    - Users who click that reaction join a lineup (max 5).
    - Maintains ONE lineup message in-channel:
        * first join -> post lineup message
        * joins/leaves -> edit lineup message
    - /clear: clears lineup AND disregards previous role mentions
              (removes bot's ✅ on old anchor messages and forgets them).
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # ✅ configure these
        self.target_role_ids = {776328568036392972, 1282865161945874543, 1416872124236431490}  # <-- replace with real role IDs
        self.reaction_emoji = "✅"  # use unicode; for custom emoji, set to its ID (int) and matcher will handle it
        self.max_participants = 5

        # lineup state
        self.participants_order: list[int] = []        # preserves join order
        self.participants_names: dict[int, str] = {}   # user_id -> display name

        # single "lineup message" we keep updating
        self.lineup_channel_id: int | None = None
        self.lineup_message_id: int | None = None

        # "anchor" messages (channel_id, message_id) where the bot reacted after a role mention
        # used so only those messages accept reactions for the lineup
        self.anchor_messages: set[tuple[int, int]] = set()

    # ----------------- lifecycle -----------------
    @commands.Cog.listener()
    async def on_ready(self):
        # Reset lineup and anchors on connect/hot-reload
        self.participants_order.clear()
        self.participants_names.clear()
        self.anchor_messages.clear()
        print("[Reactions] Lineup and anchors reset on_ready.")

    # ----------------- helpers -----------------
    def _emoji_matches(self, emoji_obj, expect) -> bool:
        """Compare a payload/Reaction emoji to our configured emoji."""
        if isinstance(expect, int):  # custom emoji id
            return getattr(emoji_obj, "id", None) == expect
        # unicode: match by name or string
        name = getattr(emoji_obj, "name", None)
        return (name == str(expect)) or (str(emoji_obj) == str(expect))

    def _is_anchor(self, channel_id: int, message_id: int) -> bool:
        return (channel_id, message_id) in self.anchor_messages

    async def _add_user(self, user_id: int, display_name: str) -> bool:
        """Add user if not present and there is room. Returns True if added."""
        if user_id in self.participants_names:
            return False
        if len(self.participants_order) >= self.max_participants:
            return False
        self.participants_order.append(user_id)
        self.participants_names[user_id] = display_name
        return True

    async def _remove_user(self, user_id: int) -> bool:
        """Remove user if present. Returns True if removed."""
        if user_id not in self.participants_names:
            return False
        self.participants_order.remove(user_id)
        self.participants_names.pop(user_id, None)
        return True

    def _lineup_text(self) -> str:
        if not self.participants_order:
            return "📭 **Lineup is empty.** React with ✅ to join."
        names = [self.participants_names[uid] for uid in self.participants_order]
        lines = [f"{i+1}. {n}" for i, n in enumerate(names)]
        header = "📋 **Current Lineup**"
        if len(self.participants_order) == self.max_participants:
            mentions = " ".join(f"<@{uid}>" for uid in self.participants_order)
            header = f"📋 **Current Lineup (READY)** — {mentions}"
        return f"{header}\n" + "\n".join(lines)

    async def _ensure_lineup_message(self, channel: discord.abc.Messageable):
        """
        Ensure we have a lineup message to edit.
        If our stored message is gone, post a new one and store its ids.
        """
        if self.lineup_channel_id and self.lineup_message_id:
            ch = self.bot.get_channel(self.lineup_channel_id)
            if ch:
                try:
                    await ch.fetch_message(self.lineup_message_id)
                    return  # still exists
                except Exception:
                    pass
        msg = await channel.send(self._lineup_text())
        self.lineup_channel_id = msg.channel.id
        self.lineup_message_id = msg.id

    async def _update_lineup_message(self, channel: discord.abc.Messageable):
        """Edit the single lineup message; create it if missing."""
        await self._ensure_lineup_message(channel)
        ch = self.bot.get_channel(self.lineup_channel_id) if self.lineup_channel_id else None
        if not ch or not self.lineup_message_id:
            return
        try:
            msg = await ch.fetch_message(self.lineup_message_id)
            await msg.edit(content=self._lineup_text())
        except Exception:
            # recreate if it was deleted
            msg2 = await channel.send(self._lineup_text())
            self.lineup_channel_id = msg2.channel.id
            self.lineup_message_id = msg2.id

    async def _remove_bots_reaction_on(self, channel_id: int, message_id: int):
        """Remove the bot's own reaction from a message (matching our emoji)."""
        ch = self.bot.get_channel(channel_id)
        if not ch:
            return
        try:
            msg = await ch.fetch_message(message_id)
        except Exception:
            return
        for r in msg.reactions:
            if self._emoji_matches(r.emoji, self.reaction_emoji):
                try:
                    await msg.remove_reaction(r.emoji, self.bot.user)
                except Exception:
                    pass

    # ----------------- listeners -----------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author == self.bot.user:
            return
        # Add the bot's reaction when a watched role is mentioned, and record this as an anchor.
        if any(role.id in self.target_role_ids for role in message.role_mentions):
            try:
                await message.add_reaction(self.reaction_emoji)
                self.anchor_messages.add((message.channel.id, message.id))

                # optional: auto-add author if room
                if await self._add_user(message.author.id, message.author.display_name):
                    await self._update_lineup_message(message.channel)
            except Exception as e:
                print(f"⚠️ Reaction/anchor setup failed: {e}")

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User | discord.Member):
        if user == self.bot.user:
            return
        if not self._emoji_matches(reaction.emoji, self.reaction_emoji):
            return
        if not self._is_anchor(reaction.message.channel.id, reaction.message.id):
            return

        display = user.display_name if isinstance(user, discord.Member) else user.name
        if await self._add_user(user.id, display):
            await self._update_lineup_message(reaction.message.channel)
        elif len(self.participants_order) >= self.max_participants:
            try:
                await reaction.message.channel.send("⚠️ The lineup is already full (max 5).")
            except Exception:
                pass

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return
        if not self._emoji_matches(payload.emoji, self.reaction_emoji):
            return
        if not self._is_anchor(payload.channel_id, payload.message_id):
            return

        display = f"user_{payload.user_id}"
        guild = self.bot.get_guild(payload.guild_id) if payload.guild_id else None
        if guild:
            member = guild.get_member(payload.user_id)
            if member:
                display = member.display_name

        ch = self.bot.get_channel(payload.channel_id)
        if ch and await self._add_user(payload.user_id, display):
            await self._update_lineup_message(ch)

    @commands.Cog.listener()
    async def on_reaction_remove(self, reaction: discord.Reaction, user: discord.User | discord.Member):
        if user == self.bot.user:
            return
        if not self._emoji_matches(reaction.emoji, self.reaction_emoji):
            return
        if not self._is_anchor(reaction.message.channel.id, reaction.message.id):
            return

        if await self._remove_user(user.id):
            await self._update_lineup_message(reaction.message.channel)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return
        if not self._emoji_matches(payload.emoji, self.reaction_emoji):
            return
        if not self._is_anchor(payload.channel_id, payload.message_id):
            return

        ch = self.bot.get_channel(payload.channel_id)
        if ch and await self._remove_user(payload.user_id):
            await self._update_lineup_message(ch)

    # ----------------- slash commands -----------------
    @discord.app_commands.command(
        name="clear",
        description="Clear the lineup and disregard previous role mention(s)."
    )
    async def clear(self, interaction: discord.Interaction):
        # Defer immediately to avoid 'Unknown interaction'
        await interaction.response.defer(ephemeral=True, thinking=True)

        # 1) Clear lineup
        self.participants_order.clear()
        self.participants_names.clear()

        # 2) Remove bot's ✅ from all anchor messages and forget them
        anchors = list(self.anchor_messages)
        self.anchor_messages.clear()
        for ch_id, msg_id in anchors:
            await self._remove_bots_reaction_on(ch_id, msg_id)

        # 3) Update (or create) the lineup message in this channel
        await self._update_lineup_message(interaction.channel)

        # Finalize the deferred response
        await interaction.edit_original_response(
            content="🧹 Lineup cleared. Old mentions are no longer active."
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(ReactionCog(bot))
