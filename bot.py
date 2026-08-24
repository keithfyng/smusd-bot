import logging

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from config import AUTO_SCHEDULE_ENABLED, BOT_TOKEN
from constants import (
    WAITING_CORRECT,
    WAITING_OPTIONS,
    WAITING_QUESTION,
)
from db import init_db
from handlers import (
    addquestion_start,
    cancel,
    queue_command,
    received_correct,
    received_options,
    received_question,
    start,
    stats_command,
    vote_callback,
    testpost_command,
    testreveal_command,
)
from scheduler import setup_scheduler

logging.basicConfig(
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    level=logging.INFO,
)
# HTTP request logs include the Telegram API URL, which contains the bot token.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


async def post_init(application):
    """Runs once after the bot is built — set up DB and scheduler."""
    await init_db()

    if AUTO_SCHEDULE_ENABLED:
        setup_scheduler(application)
        logger.info("Automatic scheduling enabled.")
    else:
        logger.info("Automatic scheduling disabled; use manual commands.")

    logger.info("Bot ready.")


def main():
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # /addquestion — multi-step conversation, admin DM only
    addquestion_conv = ConversationHandler(
        entry_points=[CommandHandler("addquestion", addquestion_start)],
        states={
            WAITING_QUESTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, received_question)
            ],
            WAITING_OPTIONS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, received_options)
            ],
            WAITING_CORRECT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, received_correct)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(addquestion_conv)
    app.add_handler(
        CallbackQueryHandler(vote_callback, pattern=r"^vote_", block=False)
    )
    app.add_handler(CommandHandler("queue", queue_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("testpost", testpost_command))
    app.add_handler(CommandHandler("testreveal", testreveal_command))

    logger.info("Polling for updates…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
