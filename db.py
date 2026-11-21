import os
import time
from typing import Optional

import aiosqlite

DB_PATH = os.getenv("DB_PATH", "modbot.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS infractions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id     INTEGER NOT NULL,
    user_id      INTEGER NOT NULL,
    moderator_id INTEGER NOT NULL,
    action       TEXT    NOT NULL,
    reason       TEXT    NOT NULL,
    created_at   INTEGER NOT NULL,
    expires_at   INTEGER,
    active       INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_infractions_user ON infractions (guild_id, user_id);
CREATE INDEX IF NOT EXISTS idx_infractions_expiry ON infractions (action, active, expires_at);

CREATE TABLE IF NOT EXISTS log_channels (
    guild_id   INTEGER NOT NULL,
    log_type   TEXT    NOT NULL,
    channel_id INTEGER NOT NULL,
    PRIMARY KEY (guild_id, log_type)
);
"""


class Database:
    def __init__(self, path: str = DB_PATH):
        self.path = path
        self.conn: Optional[aiosqlite.Connection] = None

    async def connect(self):
        folder = os.path.dirname(self.path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.executescript(SCHEMA)
        await self.conn.commit()

    async def close(self):
        if self.conn:
            await self.conn.close()

    # ---------- log channels ----------
    async def set_log_channel(self, guild_id: int, log_type: str, channel_id: int):
        await self.conn.execute(
            "INSERT INTO log_channels (guild_id, log_type, channel_id) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, log_type) DO UPDATE SET channel_id = excluded.channel_id",
            (guild_id, log_type, channel_id),
        )
        await self.conn.commit()

    async def get_log_channel(self, guild_id: int, log_type: str) -> Optional[int]:
        cur = await self.conn.execute(
            "SELECT channel_id FROM log_channels WHERE guild_id = ? AND log_type = ?",
            (guild_id, log_type),
        )
        row = await cur.fetchone()
        return row["channel_id"] if row else None

    # ---------- infractions ----------
    async def add_infraction(
        self,
        guild_id: int,
        user_id: int,
        moderator_id: int,
        action: str,
        reason: str,
        expires_at: Optional[int] = None,
    ) -> int:
        cur = await self.conn.execute(
            "INSERT INTO infractions (guild_id, user_id, moderator_id, action, reason, created_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (guild_id, user_id, moderator_id, action, reason, int(time.time()), expires_at),
        )
        await self.conn.commit()
        return cur.lastrowid

    async def get_infractions(self, guild_id: int, user_id: int):
        cur = await self.conn.execute(
            "SELECT * FROM infractions WHERE guild_id = ? AND user_id = ? ORDER BY id DESC",
            (guild_id, user_id),
        )
        return await cur.fetchall()

    async def get_infraction(self, guild_id: int, case_id: int):
        cur = await self.conn.execute(
            "SELECT * FROM infractions WHERE guild_id = ? AND id = ?", (guild_id, case_id)
        )
        return await cur.fetchone()

    async def count_infractions(self, guild_id: int, user_id: int, action: str) -> int:
        cur = await self.conn.execute(
            "SELECT COUNT(*) AS c FROM infractions WHERE guild_id = ? AND user_id = ? AND action = ?",
            (guild_id, user_id, action),
        )
        row = await cur.fetchone()
        return row["c"]

    async def delete_infraction(self, guild_id: int, case_id: int):
        await self.conn.execute(
            "DELETE FROM infractions WHERE guild_id = ? AND id = ?", (guild_id, case_id)
        )
        await self.conn.commit()

    # ---------- tempbans ----------
    async def get_expired_tempbans(self, now: int):
        cur = await self.conn.execute(
            "SELECT * FROM infractions WHERE action = 'tempban' AND active = 1 "
            "AND expires_at IS NOT NULL AND expires_at <= ?",
            (now,),
        )
        return await cur.fetchall()

    async def deactivate(self, case_id: int):
        await self.conn.execute("UPDATE infractions SET active = 0 WHERE id = ?", (case_id,))
        await self.conn.commit()

    async def deactivate_tempbans(self, guild_id: int, user_id: int):
        await self.conn.execute(
            "UPDATE infractions SET active = 0 "
            "WHERE guild_id = ? AND user_id = ? AND action = 'tempban' AND active = 1",
            (guild_id, user_id),
        )
        await self.conn.commit()
