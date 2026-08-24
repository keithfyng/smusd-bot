import json
import logging
import os
import aiosqlite
from datetime import datetime

logger = logging.getLogger(__name__)
DB_PATH = os.getenv("DB_PATH", "trivia.db")


# ─── Schema ───────────────────────────────────────────────────────────────────

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS questions (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                question         TEXT    NOT NULL,
                options          TEXT    NOT NULL,   -- JSON array of 4 strings
                correct_index    INTEGER NOT NULL,   -- 0-based index
                correct_indices  TEXT    NOT NULL DEFAULT '[]',
                explanation      TEXT    NOT NULL,   -- revealed next day
                message_id       INTEGER,            -- Telegram message ID of the question post
                sent_at          TIMESTAMP,
                revealed_at      TIMESTAMP,
                created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        columns_cursor = await db.execute("PRAGMA table_info(questions)")
        columns = {row[1] for row in await columns_cursor.fetchall()}
        if "correct_indices" not in columns:
            await db.execute(
                "ALTER TABLE questions "
                "ADD COLUMN correct_indices TEXT NOT NULL DEFAULT '[]'"
            )

        # Preserve legacy questions by converting their single answer into a
        # one-item JSON list. Keeping the old columns avoids a destructive
        # SQLite table rebuild.
        await db.execute(
            """UPDATE questions
               SET correct_indices = '[' || correct_index || ']'
               WHERE correct_indices IS NULL OR correct_indices = '[]'"""
        )
        await db.execute("""
            CREATE TABLE IF NOT EXISTS responses (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id   INTEGER NOT NULL,
                user_id       INTEGER NOT NULL,
                username      TEXT,
                first_name    TEXT,
                chosen_index  INTEGER NOT NULL,
                is_correct    INTEGER NOT NULL,   -- 1 or 0
                answered_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(question_id, user_id),
                FOREIGN KEY(question_id) REFERENCES questions(id)
            )
        """)
        await db.commit()
    logger.info("Database initialised.")


# ─── Questions ────────────────────────────────────────────────────────────────

def get_correct_indices(question) -> list[int]:
    """Decode the accepted option indices stored on a question row."""
    return json.loads(question["correct_indices"])


async def add_question(question: str, options: list, correct_indices: list[int]) -> int:
    if not correct_indices:
        raise ValueError("At least one correct answer is required")

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO questions
               (question, options, correct_index, correct_indices, explanation)
               VALUES (?, ?, ?, ?, ?)""",
            (
                question,
                json.dumps(options),
                correct_indices[0],
                json.dumps(correct_indices),
                "",
            )
        )
        await db.commit()
        return cursor.lastrowid

async def get_question_by_id(question_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM questions WHERE id = ?", (question_id,))
        return await cur.fetchone()

async def get_next_unsent_question():
    """Returns the oldest question that hasn't been posted yet."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM questions WHERE sent_at IS NULL ORDER BY id ASC LIMIT 1"
        )
        return await cur.fetchone()

async def get_latest_unrevealed_question():
    """Returns the most recently sent question whose answer hasn't been revealed."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT * FROM questions
               WHERE sent_at IS NOT NULL AND revealed_at IS NULL
               ORDER BY sent_at DESC LIMIT 1"""
        )
        return await cur.fetchone()

async def get_latest_sent_question():
    """Returns the most recently posted question (revealed or not)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM questions WHERE sent_at IS NOT NULL ORDER BY sent_at DESC LIMIT 1"
        )
        return await cur.fetchone()

async def get_queue():
    """Returns all unsent questions in insertion order."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM questions WHERE sent_at IS NULL ORDER BY id ASC"
        )
        return await cur.fetchall()

async def mark_question_sent(question_id: int, message_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE questions SET sent_at = ?, message_id = ? WHERE id = ?",
            (datetime.utcnow(), message_id, question_id)
        )
        await db.commit()

async def mark_question_revealed(question_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE questions SET revealed_at = ? WHERE id = ?",
            (datetime.utcnow(), question_id)
        )
        await db.commit()


# ─── Responses ────────────────────────────────────────────────────────────────

async def record_response(
    question_id: int, user_id: int, username: str,
    first_name: str, chosen_index: int, correct_indices: list[int]
) -> bool:
    """
    Records a vote. Returns True on success, False if the user already voted.
    """
    is_correct = 1 if chosen_index in correct_indices else 0
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                """INSERT INTO responses
                   (question_id, user_id, username, first_name, chosen_index, is_correct)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (question_id, user_id, username, first_name, chosen_index, is_correct)
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False   # UNIQUE constraint: already voted

async def get_user_vote(question_id: int, user_id: int):
    """Returns the user's vote row, or None if they haven't voted."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM responses WHERE question_id = ? AND user_id = ?",
            (question_id, user_id)
        )
        return await cur.fetchone()

async def get_vote_counts(question_id: int) -> dict:
    """Returns {option_index: count} for a question."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """SELECT chosen_index, COUNT(*) as count
               FROM responses WHERE question_id = ?
               GROUP BY chosen_index""",
            (question_id,)
        )
        rows = await cur.fetchall()
        return {row[0]: row[1] for row in rows}

async def get_summary_stats(question_id: int):
    """Returns (total_votes, total_correct) for a question."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT COUNT(*), COALESCE(SUM(is_correct), 0) FROM responses WHERE question_id = ?",
            (question_id,)
        )
        row = await cur.fetchone()
        return row[0] or 0, row[1] or 0
