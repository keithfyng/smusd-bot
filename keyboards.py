from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from constants import OPTION_LABELS


def build_question_keyboard(question_id: int, options: list) -> InlineKeyboardMarkup:
    """
    Keyboard shown while voting is open. Results stay hidden until reveal.
    All users see the same keyboard — personal feedback goes in the popup toast.
    """
    buttons = []

    for i, option in enumerate(options):
        label = f"{OPTION_LABELS[i]})  {option}"
        buttons.append([
            InlineKeyboardButton(label, callback_data=f"vote_{question_id}_{i}")
        ])

    return InlineKeyboardMarkup(buttons)


def build_revealed_keyboard(question_id: int, options: list, correct_indices: list[int], vote_counts: dict) -> InlineKeyboardMarkup:
    """
    Keyboard shown after the answer is revealed. Marks correct/wrong options.
    """
    total = sum(vote_counts.values())
    buttons = []

    for i, option in enumerate(options):
        marker = "✅" if i in correct_indices else "❌"
        count  = vote_counts.get(i, 0)
        pct    = round((count / total) * 100) if total > 0 else 0
        label  = f"{marker} {OPTION_LABELS[i]})  {option}   {count} ({pct}%)"
        # Keep callback data so clicks don't error, but vote_callback handles already-voted
        buttons.append([
            InlineKeyboardButton(label, callback_data=f"vote_{question_id}_{i}")
        ])

    return InlineKeyboardMarkup(buttons)
