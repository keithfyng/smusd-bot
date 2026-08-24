# Fun Fact Bot

A Telegram trivia bot that queues multiple-choice questions, records one vote
per participant, and reveals all accepted answers with group statistics.

## Local setup

1. Install Python 3.12.4.
2. Create and activate a virtual environment.
3. Install dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

4. Copy `.env.example` to `.env` and replace every placeholder with the real
   Telegram configuration.
5. Start the bot:

   ```powershell
   python bot.py
   ```

Never commit `.env` or the SQLite database.

## Admin commands

- `/addquestion` — add a question to the queue
- `/queue` — view queued questions
- `/stats` or `/stats <id>` — view voting statistics
- `/testpost` — immediately post the next queued question
- `/testreveal` — immediately reveal the latest unrevealed question

## Railway deployment

1. Create a Railway service from this GitHub repository.
2. Add every variable from `.env.example` using real values. Set
   `DB_PATH=/data/trivia.db`.
3. Attach a persistent Railway Volume to the service at `/data`.
4. Set the service start command to `python bot.py`.
5. Keep the service at one replica and stop any local copy using the same bot
   token before deploying.

No public domain is required because the bot uses Telegram long polling.

Railway reads `.python-version` and uses Python 3.12.4, matching the version
used to develop and test this bot.
