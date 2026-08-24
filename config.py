import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN     = os.getenv("BOT_TOKEN")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0"))
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID", "0"))
QUESTION_TIME = os.getenv("QUESTION_TIME", "09:00")   # HH:MM in local timezone
TIMEZONE      = os.getenv("TIMEZONE", "Asia/Singapore")
AUTO_SCHEDULE_ENABLED = (
    os.getenv("AUTO_SCHEDULE_ENABLED", "true").strip().lower() == "true"
)
