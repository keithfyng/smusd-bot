import json
import logging

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from config import ADMIN_USER_ID
from constants import (
    WAITING_QUESTION, WAITING_OPTIONS, WAITING_CORRECT,
    OPTION_LABELS,
)
import db

logger = logging.getLogger(__name__)


# ─── Admin guard ──────────────────────────────────────────────────────────────

async def admin_only(update: Update) -> bool:
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("⛔ You're not authorised to use this command.")
        return False
    return True


# ─── /start ───────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 I'm your trivia bot!\n\n"
        "I post a daily quiz question to the group and reveal the answer the next day.\n\n"
        "*Admin commands (DM me):*\n"
        "/addquestion — add a question to the queue\n"
        "/queue — view upcoming questions\n"
        "/stats — stats for the latest question\n"
        "/stats <id> — stats for a specific question",
        parse_mode="Markdown",
    )


# ─── /addquestion — multi-step conversation ───────────────────────────────────

async def addquestion_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update):
        return ConversationHandler.END

    context.user_data.clear()
    await update.message.reply_text(
        "📝 *New question — step 1/3*\n\nSend me the question text:",
        parse_mode="Markdown",
    )
    return WAITING_QUESTION


async def received_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["question"] = update.message.text.strip()
    await update.message.reply_text(
        "👍 Got it!\n\n"
        "*Step 2/3 — Answer options*\n\n"
        "Send me the 4 options, one per line:\n\n"
        "_Example:_\n"
        "8 minutes\n8 hours\n8 seconds\n8 days",
        parse_mode="Markdown",
    )
    return WAITING_OPTIONS


async def received_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = [l.strip() for l in update.message.text.strip().splitlines() if l.strip()]

    if len(lines) != 4:
        await update.message.reply_text(
            f"⚠️ I need exactly 4 options — got {len(lines)}. Please send them one per line:"
        )
        return WAITING_OPTIONS

    context.user_data["options"] = lines
    preview = "\n".join(f"{OPTION_LABELS[i]})  {l}" for i, l in enumerate(lines))

    await update.message.reply_text(
        f"✅ Options set:\n\n{preview}\n\n"
        "*Step 3/3 — Correct answers*\n\n"
        "Which option or options are correct? Reply with letters such as A or A,C:",
        parse_mode="Markdown",
    )
    return WAITING_CORRECT


async def received_correct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.message.text.strip().upper()
    labels = answer.replace(",", " ").split()

    if not labels or any(label not in OPTION_LABELS for label in labels):
        await update.message.reply_text(
            "⚠️ Please reply with one or more of A, B, C, or D "
            "(for example: A,C):"
        )
        return WAITING_CORRECT

    correct_indices = sorted({OPTION_LABELS.index(label) for label in labels})

    question_id = await db.add_question(
        question=context.user_data["question"],
        options=context.user_data["options"],
        correct_indices=correct_indices,
    )

    queue    = await db.get_queue()
    position = len(queue)   # already includes the one just added
    options  = context.user_data["options"]

    preview = "\n".join(
        f"{'✅' if i in correct_indices else '❌'}  {OPTION_LABELS[i]})  {opt}"
        for i, opt in enumerate(options)
    )

    await update.message.reply_text(
        f"🎉 *Question #{question_id} added!*\n"
        f"Position in queue: {position}\n\n"
        f"_{context.user_data['question']}_\n\n"
        f"{preview}",
        parse_mode="Markdown",
    )

    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelled. No question was added.")
    return ConversationHandler.END


# ─── Vote callback ────────────────────────────────────────────────────────────

async def _answer_vote_query(query, *args, **kwargs):
    """Answer a button tap without letting Telegram errors escape the task."""
    try:
        await query.answer(*args, **kwargs)
    except Exception:
        logger.exception("Could not send vote feedback")


async def vote_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    # Parse callback data: "vote_{question_id}_{chosen_index}"
    parts = query.data.split("_")
    question_id   = int(parts[1])
    chosen_index  = int(parts[2])
    user          = update.effective_user

    question = await db.get_question_by_id(question_id)
    if not question:
        await _answer_vote_query(query, "Question not found.", show_alert=True)
        return

    correct_indices = db.get_correct_indices(question)
    already_revealed = question["revealed_at"] is not None

    # Check for existing vote
    existing = await db.get_user_vote(question_id, user.id)

    if existing:
        voted_label = OPTION_LABELS[existing["chosen_index"]]
        if already_revealed:
            result = "✅ Correct!" if existing["is_correct"] else "❌ Wrong!"
            await _answer_vote_query(
                query,
                f"You picked {voted_label}) — {result}", show_alert=True
            )
        else:
            await _answer_vote_query(
                query,
                f"You already voted for {voted_label})! Come back tomorrow for the reveal. 🤫",
                show_alert=True,
            )
        return   # Don't update keyboard on repeat taps

    # Record the new vote
    try:
        success = await db.record_response(
            question_id=question_id,
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            chosen_index=chosen_index,
            correct_indices=correct_indices,
        )
    except Exception:
        logger.exception("Unexpected error while recording a vote")
        await _answer_vote_query(
            query, "Couldn't record your vote — try again.", show_alert=True
        )
        return

    if not success:
        existing = await db.get_user_vote(question_id, user.id)
        if existing:
            voted_label = OPTION_LABELS[existing["chosen_index"]]
            await _answer_vote_query(
                query, f"You already voted for {voted_label})!", show_alert=True
            )
            return
        await _answer_vote_query(
            query, "Couldn't record your vote — try again.", show_alert=True
        )
        return

    await _answer_vote_query(
        query,
        f"Voted {OPTION_LABELS[chosen_index]})! Answer reveals tomorrow at noon. 🕛"
    )

# ─── /queue ───────────────────────────────────────────────────────────────────

async def queue_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update):
        return

    queue = await db.get_queue()

    if not queue:
        await update.message.reply_text(
            "📭 Queue is empty! Add questions with /addquestion."
        )
        return

    lines = [f"📋 *Queue — {len(queue)} question{'s' if len(queue) != 1 else ''} waiting:*\n"]
    for pos, q in enumerate(queue, 1):
        options = json.loads(q["options"])
        correct_indices = db.get_correct_indices(q)
        correct_answers = ", ".join(
            f"{OPTION_LABELS[i]}) {options[i]}" for i in correct_indices
        )
        snippet = q["question"][:55] + ("…" if len(q["question"]) > 55 else "")
        lines.append(
            f"*{pos}.* [#{q['id']}]  {snippet}\n"
            f"     ✅  {correct_answers}\n"
        )

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ─── /stats ───────────────────────────────────────────────────────────────────

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update):
        return

    if context.args:
        try:
            question_id = int(context.args[0])
            question    = await db.get_question_by_id(question_id)
        except ValueError:
            await update.message.reply_text("⚠️ Usage: /stats  or  /stats <question_id>")
            return
    else:
        question = await db.get_latest_sent_question()

    if not question:
        await update.message.reply_text("No questions have been posted yet.")
        return

    options       = json.loads(question["options"])
    correct_indices = db.get_correct_indices(question)
    vote_counts   = await db.get_vote_counts(question["id"])
    total, total_correct = await db.get_summary_stats(question["id"])
    correct_pct   = round((total_correct / total) * 100) if total > 0 else 0

    lines = [
        f"📊 *Stats — Question #{question['id']}*",
        f"_{question['question']}_\n",
    ]
    for i, option in enumerate(options):
        count  = vote_counts.get(i, 0)
        pct    = round((count / total) * 100) if total > 0 else 0
        marker = "✅" if i in correct_indices else "❌"
        lines.append(f"{marker}  {OPTION_LABELS[i]})  {option}  —  {count} vote{'s' if count != 1 else ''} ({pct}%)")

    lines.append(f"\n👥 Total votes:  {total}")
    lines.append(f"🎯 Got it right: {total_correct} ({correct_pct}%)")

    status = "🔓 Revealed" if question["revealed_at"] else "⏳ Awaiting reveal"
    lines.append(f"\nStatus: {status}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ─── Manual posting and revealing ────────────────────────────────────────────

async def post_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually trigger posting the next question right now."""
    if not await admin_only(update):
        return

    from scheduler import _post_question
    next_q = await db.get_next_unsent_question()
    if not next_q:
        await update.message.reply_text("Queue is empty — add a question first with /addquestion.")
        return

    await _post_question(context, next_q)
    await update.message.reply_text("✅ Question posted to the group!")


async def reveal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually trigger revealing the latest unrevealed question right now."""
    if not await admin_only(update):
        return

    from scheduler import _reveal_question
    unrevealed = await db.get_latest_unrevealed_question()
    if not unrevealed:
        await update.message.reply_text("No unrevealed question found. Post one first with /post.")
        return

    await _reveal_question(context, unrevealed)
    await update.message.reply_text("✅ Answer revealed in the group!")
