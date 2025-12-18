import os
from datetime import datetime
from typing import List, Optional, Tuple

import aiosqlite


class Database:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = os.getenv("DB_PATH", "vaahaka_credits.db")
        self.db_path = db_path

    async def init_db(self):
        """Initialize the database schema."""
        async with aiosqlite.connect(self.db_path) as db:
            # Credits table stores user totals
            await db.execute("""
                CREATE TABLE IF NOT EXISTS credits (
                    user_id INTEGER PRIMARY KEY,
                    points INTEGER DEFAULT 0,
                    last_upload DATETIME
                )
            """)

            # Uploads table tracks individual PDF uploads with hash for duplicate prevention
            await db.execute("""
                CREATE TABLE IF NOT EXISTS uploads (
                    file_hash TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    file_name TEXT NOT NULL,
                    page_count INTEGER NOT NULL,
                    upload_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES credits (user_id)
                )
            """)

            # Config table stores bot configuration
            await db.execute("""
                CREATE TABLE IF NOT EXISTS config (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

            # Listened channels table stores which channels the bot should monitor for PDFs
            # (persisted across restarts)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS listened_channels (
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (guild_id, channel_id)
                )
            """)

            # Create indexes for faster queries
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_user_uploads
                ON uploads(user_id)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_listened_channels_guild
                ON listened_channels(guild_id)
            """)

            await db.commit()

    async def add_upload(
        self, user_id: int, file_hash: str, file_name: str, page_count: int
    ) -> bool:
        """
        Add a new PDF upload and update user credits.
        Returns True if successful, False if duplicate.
        """
        async with aiosqlite.connect(self.db_path) as db:
            # Check if file hash already exists
            async with db.execute(
                "SELECT file_hash FROM uploads WHERE file_hash = ?", (file_hash,)
            ) as cursor:
                if await cursor.fetchone():
                    return False

            # Insert upload record
            await db.execute(
                """INSERT INTO uploads (file_hash, user_id, file_name, page_count)
                   VALUES (?, ?, ?, ?)""",
                (file_hash, user_id, file_name, page_count),
            )

            # Update or insert user credits
            await db.execute(
                """INSERT INTO credits (user_id, points, last_upload)
                   VALUES (?, ?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET
                   points = points + ?,
                   last_upload = ?""",
                (user_id, page_count, datetime.now(), page_count, datetime.now()),
            )

            await db.commit()
            return True

    async def get_user_stats(
        self, user_id: int
    ) -> Optional[Tuple[int, int, List[Tuple[str, int]]]]:
        """
        Get user statistics.
        Returns (total_points, rank, [(file_name, page_count), ...]) or None if user not found.
        """
        async with aiosqlite.connect(self.db_path) as db:
            # Get user points
            async with db.execute(
                "SELECT points FROM credits WHERE user_id = ?", (user_id,)
            ) as cursor:
                result = await cursor.fetchone()
                if not result:
                    return None
                points = int(result[0])

            # Get user rank
            async with db.execute(
                """SELECT COUNT(*) + 1 FROM credits
                   WHERE points > ?""",
                (points,),
            ) as cursor:
                row = await cursor.fetchone()
                # `fetchone()` is typed as possibly returning None; guard for type checkers.
                rank = int(row[0]) if row else 1

            # Get user's uploaded books
            async with db.execute(
                """SELECT file_name, page_count FROM uploads
                   WHERE user_id = ?
                   ORDER BY upload_date DESC""",
                (user_id,),
            ) as cursor:
                rows = await cursor.fetchall()
                books: List[Tuple[str, int]] = [
                    (str(file_name), int(page_count)) for file_name, page_count in rows
                ]

            return (points, rank, books)

    async def get_leaderboard(self, limit: int = 10) -> List[Tuple[int, int]]:
        """
        Get top users by points.
        Returns [(user_id, points), ...].
        """
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """SELECT user_id, points FROM credits
                   ORDER BY points DESC
                   LIMIT ?""",
                (limit,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [(int(user_id), int(points)) for user_id, points in rows]

    async def get_all_user_ids(self) -> List[int]:
        """Get all user IDs in the database."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT user_id FROM credits") as cursor:
                results = await cursor.fetchall()
                return [row[0] for row in results]

    async def get_all_users_ranked(self) -> List[Tuple[int, int]]:
        """
        Get all users ranked by points.
        Returns [(user_id, points), ...] ordered by points descending.
        """
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """SELECT user_id, points FROM credits
                   ORDER BY points DESC"""
            ) as cursor:
                rows = await cursor.fetchall()
                return [(int(user_id), int(points)) for user_id, points in rows]

    async def set_leaderboard_channel(self, channel_id: int):
        """Set the channel ID for automatic leaderboard updates."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
                ("leaderboard_channel", str(channel_id)),
            )
            await db.commit()

    async def get_leaderboard_channel(self) -> Optional[int]:
        """Get the channel ID for automatic leaderboard updates."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT value FROM config WHERE key = ?", ("leaderboard_channel",)
            ) as cursor:
                row = await cursor.fetchone()
                return int(row[0]) if row else None

    async def add_listened_channel(self, guild_id: int, channel_id: int) -> None:
        """Persist a channel ID that the bot should listen to for PDF uploads."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR IGNORE INTO listened_channels (guild_id, channel_id)
                VALUES (?, ?)
                """,
                (guild_id, channel_id),
            )
            await db.commit()

    async def remove_listened_channel(self, guild_id: int, channel_id: int) -> None:
        """Remove a channel from the persisted listen list."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                DELETE FROM listened_channels
                WHERE guild_id = ? AND channel_id = ?
                """,
                (guild_id, channel_id),
            )
            await db.commit()

    async def clear_listened_channels(self, guild_id: int) -> None:
        """Clear all listened channels for a guild."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                DELETE FROM listened_channels
                WHERE guild_id = ?
                """,
                (guild_id,),
            )
            await db.commit()

    async def get_listened_channels(self, guild_id: int) -> List[int]:
        """
        Get the persisted list of listened channels for a guild.

        Returns a list of channel IDs. If empty, it means "no configured channels".
        (Your bot logic can decide whether empty means listen-to-all or listen-to-none.)
        """
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT channel_id
                FROM listened_channels
                WHERE guild_id = ?
                ORDER BY added_at ASC
                """,
                (guild_id,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [int(row[0]) for row in rows]

    async def is_channel_listened(self, guild_id: int, channel_id: int) -> bool:
        """Check if a channel is in the persisted listen list for a guild."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT 1
                FROM listened_channels
                WHERE guild_id = ? AND channel_id = ?
                LIMIT 1
                """,
                (guild_id, channel_id),
            ) as cursor:
                return await cursor.fetchone() is not None
