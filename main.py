import math
import os

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View
from dotenv import load_dotenv

from database import Database
from pdf_processor import PDFProcessor

# Load environment variables
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")

# Dev mode: when enabled, bypass admin-only permission checks for slash commands.
# Set DEV_MODE=1 (or true/yes/on) in your environment/.env to enable.
DEV_MODE = os.getenv("DEV_MODE", "").strip().lower() in {"1", "true", "yes", "on"}

# Initialize bot
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
db = Database()
pdf_processor = PDFProcessor()


def admin_only_or_dev(interaction: discord.Interaction) -> bool:
    """Allow everyone in DEV_MODE; otherwise require administrator permissions."""
    if DEV_MODE:
        return True

    perms = getattr(getattr(interaction, "user", None), "guild_permissions", None)
    return bool(getattr(perms, "administrator", False))


async def send_upload_notification(user: discord.User, file_name: str, page_count: int):
    """Send a rich notification when a user uploads a PDF."""
    channel_id = await db.get_leaderboard_channel()
    if not channel_id:
        return

    channel = bot.get_channel(channel_id)
    if not isinstance(channel, discord.abc.Messageable):
        return

    # Get user's updated stats
    result = await db.get_user_stats(user.id)
    if not result:
        return

    total_points, rank, _ = result

    # Create rich embed
    embed = discord.Embed(
        title="📚 NEW BOOK UPLOADED!",
        description=f"**{user.display_name}** has uploaded a new book!",
        color=discord.Color.green(),
        timestamp=discord.utils.utcnow(),
    )

    # Set user's avatar
    embed.set_thumbnail(url=user.display_avatar.url)

    # Add fields
    embed.add_field(name="📖 Book", value=f"`{file_name}`", inline=False)
    embed.add_field(
        name="⭐ Points Earned", value=f"**+{page_count:,}** credits", inline=True
    )
    embed.add_field(
        name="🏆 Total Credits", value=f"**{total_points:,}** credits", inline=True
    )
    embed.add_field(name="📊 Rank", value=f"**#{rank}**", inline=True)

    # Set footer with user info
    embed.set_footer(
        text=f"Uploaded by {user.name}",
        icon_url=user.display_avatar.url,
    )

    await channel.send(embed=embed)


async def update_public_leaderboard():
    """Fetches the leaderboard channel and sends an updated leaderboard."""
    channel_id = await db.get_leaderboard_channel()
    if not channel_id:
        return

    channel = bot.get_channel(channel_id)
    if not isinstance(channel, discord.abc.Messageable):
        return

    guild = getattr(channel, "guild", None)

    # Fetch top users
    top_users = await db.get_leaderboard(10)
    if not top_users:
        return

    # Create rich embed (match "new book uploaded" style)
    embed = discord.Embed(
        title="🏆 LEADERBOARD UPDATED!",
        description="Top contributors right now:",
        color=discord.Color.green(),
        timestamp=discord.utils.utcnow(),
    )

    if guild and guild.icon:
        embed.set_thumbnail(url=guild.icon.url)

    medals = ["🥇", "🥈", "🥉"]
    leaderboard_text = ""

    for idx, (user_id, points) in enumerate(top_users, 1):
        try:
            user = await bot.fetch_user(user_id)
            user_name = user.display_name
        except Exception as e:
            print(f"Error fetching user {user_id}: {e}")
            user_name = f"User {user_id}"

        if idx <= 3:
            medal = medals[idx - 1]
        else:
            medal = f"**{idx}.**"

        leaderboard_text += f"{medal} **{user_name}** = **{points:,}** credits\n"

    embed.add_field(name="🏅 Top 10", value=leaderboard_text, inline=False)

    if guild and guild.icon:
        embed.set_footer(
            text="Vaahaka Credits • Auto-updated leaderboard",
            icon_url=guild.icon.url,
        )
    else:
        embed.set_footer(text="Vaahaka Credits • Auto-updated leaderboard")

    await channel.send(embed=embed)


@bot.event
async def on_ready():
    """Initialize database and sync commands when bot is ready."""
    print(f"{bot.user} has connected to Discord!")
    await db.init_db()

    # Sync commands to guild
    if GUILD_ID:
        guild = discord.Object(id=int(GUILD_ID))
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
        print(f"Commands synced to guild {GUILD_ID}")
    else:
        await bot.tree.sync()
        print("Commands synced globally")


@bot.event
async def on_message(message):
    """Monitor messages for PDF uploads."""
    # Ignore bot's own messages
    if message.author.bot:
        return

    # Process commands first
    await bot.process_commands(message)

    # Check for PDF attachments
    for attachment in message.attachments:
        if attachment.content_type == "application/pdf" or pdf_processor.is_pdf(
            attachment.filename
        ):
            try:
                # Download the PDF
                file_data = await attachment.read()

                # Process the PDF
                result = await pdf_processor.process_pdf(file_data, attachment.filename)
                if not result:
                    await message.add_reaction("❌")
                    continue

                file_hash, page_count = result

                # Add to database
                success = await db.add_upload(
                    user_id=message.author.id,
                    file_hash=file_hash,
                    file_name=attachment.filename,
                    page_count=page_count,
                )

                if success:
                    # Acknowledge with trophy reaction
                    await message.add_reaction("🏆")

                    # Send confirmation message
                    await message.channel.send(
                        f"✅ {message.author.mention} earned **{page_count:,} credits** for uploading `{attachment.filename}`!"
                    )

                    # Send upload notification to leaderboard channel
                    await send_upload_notification(
                        message.author, attachment.filename, page_count
                    )

                    # Update public leaderboard
                    await update_public_leaderboard()
                else:
                    # Duplicate file
                    await message.add_reaction("♻️")
                    await message.channel.send(
                        f"⚠️ {message.author.mention}, this PDF has already been uploaded. No credits awarded."
                    )

            except Exception as e:
                print(f"Error processing PDF upload: {e}")
                await message.add_reaction("❌")


@bot.tree.command(
    name="stats", description="View your personal credits and uploaded books"
)
async def stats(interaction: discord.Interaction):
    """Display user statistics."""
    result = await db.get_user_stats(interaction.user.id)

    if not result:
        await interaction.response.send_message(
            "You haven't uploaded any PDFs yet! Upload a PDF to earn credits.",
            ephemeral=False,
        )
        return

    points, rank, books = result

    # Create embed
    embed = discord.Embed(
        title=f"📊 Stats for {interaction.user.display_name}",
        color=discord.Color.blue(),
    )

    embed.add_field(name="Total Credits", value=f"**{points:,}** pages", inline=True)
    embed.add_field(name="Global Rank", value=f"**#{rank}**", inline=True)
    embed.add_field(name="Books Uploaded", value=f"**{len(books)}**", inline=True)

    # Add list of uploaded books
    if books:
        books_list = "\n".join(
            [f"• `{name}` - {count:,} pages" for name, count in books[:10]]
        )
        if len(books) > 10:
            books_list += f"\n... and {len(books) - 10} more"
        embed.add_field(name="📚 Your Uploads", value=books_list, inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=False)


@bot.tree.command(name="leaderboard", description="View the top contributors")
async def leaderboard(interaction: discord.Interaction):
    """Display the leaderboard."""
    top_users = await db.get_leaderboard(10)

    if not top_users:
        await interaction.response.send_message(
            "No one has uploaded any PDFs yet! Be the first to earn credits.",
            ephemeral=True,
        )
        return

    # Create rich embed (match "new book uploaded" style)
    embed = discord.Embed(
        title="🏆 LEADERBOARD",
        description=f"Requested by **{interaction.user.display_name}**",
        color=discord.Color.green(),
        timestamp=discord.utils.utcnow(),
    )

    if interaction.guild and interaction.guild.icon:
        embed.set_thumbnail(url=interaction.guild.icon.url)

    medals = ["🥇", "🥈", "🥉"]
    leaderboard_text = ""

    for idx, (user_id, points) in enumerate(top_users, 1):
        try:
            user = await bot.fetch_user(user_id)
            # Prefer display_name when available, fall back to username/name
            user_name = getattr(user, "display_name", None) or getattr(
                user, "name", f"User {user_id}"
            )
        except Exception as e:
            # Log the error and fall back to a generic name
            print(f"Error fetching user {user_id}: {e}")
            user_name = f"User {user_id}"

        if idx <= 3:
            medal = medals[idx - 1]
        else:
            medal = f"**{idx}.**"

        leaderboard_text += f"{medal} **{user_name}** = **{points:,}** credits\n"

    embed.add_field(name="🏅 Top 10", value=leaderboard_text, inline=False)

    embed.set_footer(
        text=f"Requested by {interaction.user.name}",
        icon_url=interaction.user.display_avatar.url,
    )

    await interaction.response.send_message(embed=embed)


class AllTimeView(View):
    """Pagination view for all-time rankings."""

    def __init__(self, all_users, current_page=0, per_page=20, guild_icon_url=None):
        super().__init__(timeout=180)
        self.all_users = all_users
        self.current_page = current_page
        self.per_page = per_page
        self.total_pages = math.ceil(len(all_users) / per_page)
        self.guild_icon_url = guild_icon_url

        # Update button states
        self.update_buttons()

    def update_buttons(self):
        """Enable/disable buttons based on current page."""
        # Clear existing buttons
        self.clear_items()

        # Previous button
        prev_button = Button(label="◀ Previous", style=discord.ButtonStyle.primary)
        prev_button.callback = self.previous_page
        prev_button.disabled = self.current_page == 0
        self.add_item(prev_button)

        # Page indicator
        page_button = Button(
            label=f"Page {self.current_page + 1}/{self.total_pages}",
            style=discord.ButtonStyle.secondary,
            disabled=True,
        )
        self.add_item(page_button)

        # Next button
        next_button = Button(label="Next ▶", style=discord.ButtonStyle.primary)
        next_button.callback = self.next_page
        next_button.disabled = self.current_page >= self.total_pages - 1
        self.add_item(next_button)

    async def get_embed(self):
        """Generate embed for current page."""
        start_idx = self.current_page * self.per_page
        end_idx = min(start_idx + self.per_page, len(self.all_users))
        page_users = self.all_users[start_idx:end_idx]

        embed = discord.Embed(
            title="📊 ALL-TIME RANKINGS",
            description="Complete ranking of all contributors",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow(),
        )

        icon_url = self.guild_icon_url
        if not icon_url and bot.user:
            icon_url = bot.user.display_avatar.url

        if icon_url:
            embed.set_thumbnail(url=icon_url)

        embed.add_field(
            name="👥 Total Contributors",
            value=f"**{len(self.all_users)}**",
            inline=True,
        )
        embed.add_field(
            name="📄 Page",
            value=f"**{self.current_page + 1}/{self.total_pages}**",
            inline=True,
        )

        medals = ["🥇", "🥈", "🥉"]
        ranking_text = ""

        for idx, (user_id, points) in enumerate(page_users, start=start_idx + 1):
            try:
                user = await bot.fetch_user(user_id)
                user_name = user.display_name
            except Exception as e:
                print(f"Error fetching user {user_id}: {e}")
                user_name = f"User {user_id}"

            if idx <= 3:
                medal = medals[idx - 1]
            else:
                medal = f"**{idx}.**"

            ranking_text += f"{medal} **{user_name}** = **{points:,}** credits\n"

        # Use description (4096 chars) instead of a field value (1024 chars) to avoid field-length limits.
        embed.description = f"Complete ranking of all contributors\n\n{ranking_text}"
        if icon_url:
            embed.set_footer(
                text="Vaahaka Credits • Use the buttons to navigate pages",
                icon_url=icon_url,
            )
        else:
            embed.set_footer(text="Vaahaka Credits • Use the buttons to navigate pages")

        return embed

    async def previous_page(self, interaction: discord.Interaction):
        """Go to previous page."""
        self.current_page -= 1
        self.update_buttons()
        embed = await self.get_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def next_page(self, interaction: discord.Interaction):
        """Go to next page."""
        self.current_page += 1
        self.update_buttons()
        embed = await self.get_embed()
        await interaction.response.edit_message(embed=embed, view=self)


@bot.tree.command(
    name="alltime", description="View complete all-time rankings of all contributors"
)
async def alltime(interaction: discord.Interaction):
    """Display the complete all-time rankings with pagination."""
    all_users = await db.get_all_users_ranked()

    if not all_users:
        await interaction.response.send_message(
            "No one has uploaded any PDFs yet! Be the first to earn credits.",
            ephemeral=True,
        )
        return

    # Create pagination view
    guild_icon_url = None
    if interaction.guild and interaction.guild.icon:
        guild_icon_url = interaction.guild.icon.url

    view = AllTimeView(all_users, guild_icon_url=guild_icon_url)
    embed = await view.get_embed()

    await interaction.response.send_message(embed=embed, view=view)


@bot.tree.command(
    name="set_leaderboard_channel",
    description="Set the channel for automatic leaderboard updates (Admin only)",
)
@app_commands.check(admin_only_or_dev)
async def set_leaderboard_channel(
    interaction: discord.Interaction, channel: discord.TextChannel
):
    """Set the channel where leaderboard updates will be posted."""
    await db.set_leaderboard_channel(channel.id)
    await interaction.response.send_message(
        f"✅ Leaderboard updates bound to {channel.mention}", ephemeral=True
    )


@set_leaderboard_channel.error
async def set_leaderboard_channel_error(interaction: discord.Interaction, error):
    """Handle permission/check errors for set_leaderboard_channel command."""
    if isinstance(
        error,
        (
            app_commands.errors.MissingPermissions,
            app_commands.errors.CheckFailure,
        ),
    ):
        await interaction.response.send_message(
            "❌ You need administrator permissions to use this command.", ephemeral=True
        )


@bot.tree.command(
    name="run_leaderboard_listner",
    description="Scan channel history for existing PDFs (Admin only)",
)
@app_commands.check(admin_only_or_dev)
async def run_leaderboard_listner(interaction: discord.Interaction):
    """Scan channel history to find and process all existing PDFs."""
    await interaction.response.defer(ephemeral=True)

    channel = interaction.channel

    # Use isinstance to check if the channel supports message history
    if not isinstance(channel, discord.abc.Messageable):
        await interaction.followup.send(
            "❌ This command must be run in a text channel, thread, or DM that supports message history."
        )
        return

    processed_count = 0
    duplicate_count = 0
    error_count = 0
    scanned_messages = 0

    await interaction.followup.send(
        "🔍 Starting historical scan... This may take a while. I'll report back when finished."
    )

    try:
        # Iterate through all messages in channel history (oldest_first can be set if desired)
        async for message in channel.history(limit=None):
            scanned_messages += 1

            # Skip bot messages
            if message.author and message.author.bot:
                continue

            # Check for PDF attachments
            for attachment in message.attachments:
                if attachment.content_type == "application/pdf" or pdf_processor.is_pdf(
                    attachment.filename
                ):
                    try:
                        # Download the PDF
                        file_data = await attachment.read()

                        # Process the PDF
                        result = await pdf_processor.process_pdf(
                            file_data, attachment.filename
                        )
                        if not result:
                            error_count += 1
                            continue

                        file_hash, page_count = result

                        # Add to database
                        success = await db.add_upload(
                            user_id=message.author.id,
                            file_hash=file_hash,
                            file_name=attachment.filename,
                            page_count=page_count,
                        )

                        if success:
                            processed_count += 1
                        else:
                            duplicate_count += 1

                    except Exception as e:
                        # Log error and continue scanning
                        print(
                            f"Error processing historical PDF '{attachment.filename}' from message {message.id}: {e}"
                        )
                        error_count += 1

        # Send summary
        summary = (
            f"✅ **Historical Scan Complete!**\n\n"
            f"📊 Results for channel `{getattr(channel, 'name', str(channel.id))}`:\n"
            f"• Scanned messages: **{scanned_messages}**\n"
            f"• Processed: **{processed_count}** new PDFs\n"
            f"• Duplicates: **{duplicate_count}** (skipped)\n"
            f"• Errors: **{error_count}**\n\n"
            "The leaderboard has been updated with all historical data where applicable."
        )
        await interaction.followup.send(summary)

        # Update public leaderboard if any PDFs were processed
        if processed_count > 0:
            await update_public_leaderboard()

    except Exception as e:
        # Catch any unexpected errors during the scan
        print(f"Error during historical scan in channel {channel}: {e}")
        await interaction.followup.send(f"❌ Error during scan: {e}")


@run_leaderboard_listner.error
async def run_leaderboard_listner_error(interaction: discord.Interaction, error):
    """Handle permission/check errors for run_leaderboard_listner command."""
    if isinstance(
        error,
        (
            app_commands.errors.MissingPermissions,
            app_commands.errors.CheckFailure,
        ),
    ):
        await interaction.response.send_message(
            "❌ You need administrator permissions to use this command.", ephemeral=True
        )


def main():
    """Run the bot."""
    if not DISCORD_TOKEN:
        print("Error: DISCORD_TOKEN not found in environment variables.")
        print("Please create a .env file with your Discord bot token.")
        return

    bot.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()
