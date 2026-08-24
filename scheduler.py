import json
import logging
import pytz
from datetime import time

from config import GROUP_CHAT_ID, ADMIN_USER_ID, QUESTION_TIME, TIMEZONE
from constants import OPTION_LABELS
from keyboards import build_question_keyboard, build_revealed_keyboard
import db

logger = logging.getLogger(__name__)


def setup_scheduler(application):
    """Register the daily trivia job with the bot's built-in job queue."""
    tz   = pytz.timezone(TIMEZONE)
    hour, minute = map(int, QUESTION_TIME.split(":"))

    application.job_queue.run_daily(
        callback=daily_job,
        time=time(hour=hour, minute=minute, tzinfo=tz),
        name="daily_trivia",
    )
    logger.info(f"Scheduler ready: daily at {QUESTION_TIME} {TIMEZONE}")


# ─── Daily job ────────────────────────────────────────────────────────────────

async def daily_job(context):
    """
    Runs daily at QUESTION_TIME:
      1. Reveal yesterday's answer (if any)
      2. Post today's question (if any in queue)
    """
    # Step 1 — reveal
    unrevealed = await db.get_latest_unrevealed_question()
    if unrevealed:
        await _reveal_question(context, unrevealed)
    else:
        logger.info("No unrevealed question to reveal today.")

    # Step 2 — post next question
    next_q = await db.get_next_unsent_question()
    if next_q:
        await _post_question(context, next_q)
    else:
        logger.warning("Queue is empty — nothing to post today.")
        await context.bot.send_message(
            chat_id=ADMIN_USER_ID,
            text=(
                "⚠️ *Queue is empty!*\n\n"
                "No question was posted today. Add more with /addquestion."
            ),
            parse_mode="Markdown",
        )


# ─── Post a question ──────────────────────────────────────────────────────────

async def _post_question(context, question):
    options = json.loads(question["options"])

    keyboard = build_question_keyboard(question["id"], options)

    text = (
        "🧠 *Daily Trivia!*\n\n"
        f"{question['question']}\n\n"
        "_Vote below — answer reveals tomorrow at noon!_"
    )

    msg = await context.bot.send_message(
        chat_id=GROUP_CHAT_ID,
        text=text,
        reply_markup=keyboard,
        parse_mode="Markdown",
    )

    await db.mark_question_sent(question["id"], msg.message_id)
    logger.info(f"Posted question #{question['id']} (message_id={msg.message_id})")


# ─── Reveal an answer ─────────────────────────────────────────────────────────

async def _reveal_question(context, question):
    options       = json.loads(question["options"])
    correct_indices = db.get_correct_indices(question)
    answer_lines = "\n".join(
        f"*{OPTION_LABELS[i]})  {options[i]}*" for i in correct_indices
    )
    if len(correct_indices) == 1:
        answer_text = f"The correct answer was {answer_lines}!"
    else:
        answer_text = f"The correct answers were:\n{answer_lines}"

    vote_counts              = await db.get_vote_counts(question["id"])
    total, total_correct     = await db.get_summary_stats(question["id"])
    correct_pct              = round((total_correct / total) * 100) if total > 0 else 0

    # Build per-option result lines
    result_lines = []
    for i, option in enumerate(options):
        count  = vote_counts.get(i, 0)
        pct    = round((count / total) * 100) if total > 0 else 0
        marker = "✅" if i in correct_indices else "❌"
        result_lines.append(f"{marker}  {OPTION_LABELS[i]})  {option}  —  {count} ({pct}%)")

    reveal_text = (
        f"🔓 *Answer Reveal!*\n\n"
        f"*Q:* _{question['question']}_\n\n"
        f"{answer_text}\n\n"
        f"📊 *Results — {total} vote{'s' if total != 1 else ''}:*\n"
        + "\n".join(result_lines)
        + f"\n\n🎯 *{total_correct}/{total} got it right ({correct_pct}%)*"
    )

    # Edit the original question message to show correct/wrong on the buttons
    if question["message_id"]:
        revealed_keyboard = build_revealed_keyboard(
            question["id"], options, correct_indices, vote_counts
        )
        try:
            await context.bot.edit_message_reply_markup(
                chat_id=GROUP_CHAT_ID,
                message_id=question["message_id"],
                reply_markup=revealed_keyboard,
            )
        except Exception as e:
            logger.warning(f"Could not edit original question message: {e}")

    # Send the reveal post
    await context.bot.send_message(
        chat_id=GROUP_CHAT_ID,
        text=reveal_text,
        parse_mode="Markdown",
    )

    await db.mark_question_revealed(question["id"])
    logger.info(f"Revealed question #{question['id']}")
