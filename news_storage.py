import aiosqlite
import asyncio
from datetime import datetime, timedelta
import logging

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

DATABASE_NAME = "sent_news.db"


async def init_db():
    """Initializes the SQLite database table for sent news."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS sent_news (
                news_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                channel_id INTEGER NOT NULL
            )
            """
        )
        await db.commit()
    logging.info("Database initialized successfully.")

async def is_news_sent(news_id, channel_id):
    """Checks if the news has already been sent to the specified channel."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        cursor = await db.execute('SELECT news_id FROM sent_news WHERE news_id = ? AND channel_id = ?', (news_id, channel_id))
        result = await cursor.fetchone()
        return result is not None
    
async def add_sent_news(news_id, symbol, channel_id):
    """Adds a news article ID to the sent_news table."""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        try:
            await db.execute('INSERT INTO sent_news (news_id, symbol, timestamp, channel_id) VALUES (?, ?, ?, ?)',
                             (news_id, symbol, int(datetime.now().timestamp()), channel_id))
            await db.commit()
            logging.info(f"Added news ID {news_id} for symbol {symbol} to channel {channel_id}.")
        except aiosqlite.IntegrityError:
            logging.warning(f"Attempted to add duplicate news ID {news_id} for symbol {symbol} to channel {channel_id}.")
            # This should ideally not happen if is_news_sent is checked first,
            # but good to handle for robustness.

async def clean_old_news(days_to_keep=7):
    """Removes old news entries from the database to keep it clean."""
    cutoff_timestamp = int((datetime.now() - timedelta(days=days_to_keep)).timestamp())
    async with aiosqlite.connect(DATABASE_NAME) as db:
        await db.execute('DELETE FROM sent_news WHERE timestamp < ?', (cutoff_timestamp,))
        await db.commit()
    logging.info(f"Cleaned up news entries older than {days_to_keep} days.")

if __name__ == "__main__":
    # Example usage
    async def test_news_storage():
        await init_db()
        
        test_news_id_1 = "test_news_123"
        test_news_id_2 = "test_news_456"
        test_symbol = "TEST"
        test_channel_id = 123456789

        print(f"Is news '{test_news_id_1}' sent? {await is_news_sent(test_news_id_1, test_channel_id)}")
        await add_sent_news(test_news_id_1, test_symbol, test_channel_id)
        print(f"Is news '{test_news_id_1}' sent after adding? {await is_news_sent(test_news_id_1, test_channel_id)}")

        print(f"Is news '{test_news_id_2}' sent? {await is_news_sent(test_news_id_2, test_channel_id)}")
        await add_sent_news(test_news_id_2, test_symbol, test_channel_id)
        print(f"Is news '{test_news_id_2}' sent after adding? {await is_news_sent(test_news_id_2, test_channel_id)}")

        await add_sent_news(test_news_id_1, test_symbol, test_channel_id)

        await clean_old_news(days_to_keep=0) # Set to 0 for testing purposes
        print(f"Is news '{test_news_id_1}' sent after cleanup? (0 days) {await is_news_sent(test_news_id_1, test_channel_id)}")

    asyncio.run(test_news_storage())

