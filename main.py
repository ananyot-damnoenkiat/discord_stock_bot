import discord
from discord.ext import commands, tasks
from datetime import datetime, time
import asyncio
import logging

# Import API keys and other configurations
import config
# Import custom modules
import stock_data_api
import news_storage

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Set up Discord bot with intents
intents = discord.Intents.default()
intents.message_content = True # Necessary for message content
intents.members = True # Necessary for member-related events
intents.presences = True # Necessary for presence-related events

bot = commands.Bot(command_prefix='!', intents=intents)

# Collection of stocks to track
# key: channel_id, value: set of symbols (use set to avoid duplicates)
tracked_stocks = {}

@bot.event
async def on_ready():
    logging.info(f'{bot.user} ได้เชื่อมต่อกับ Discord เรียบร้อยแล้ว!')
    await news_storage.init_db() # Start the database
    logging.info("Database initialized.")
    
    # Start tasks for stocks price updates
    daily_stock_update_morning.start()
    daily_stock_update_open.start()
    daily_stock_update_midnight.start()

    # Start tasks for news updates
    check_news_task.start()
    clean_old_news_task.start() # เริ่ม task ทำความสะอาดฐานข้อมูล

# Command for add tracking stocks
@bot.command(name='track')
async def track_stock(ctx, symbol: str):
    symbol = symbol.upper()
    if ctx.channel.id not in tracked_stocks:
        tracked_stocks[ctx.channel.id] = set()

    if symbol in tracked_stocks[ctx.channel.id]:
        await ctx.send(f"หุ้น **{symbol}** ถูกติดตามอยู่แล้วในช่องนี้")
    else:
        tracked_stocks[ctx.channel.id].add(symbol)
        await ctx.send(f"เริ่มติดตามหุ้น **{symbol}** แล้วในช่องนี้")
        logging.info(f"Tracking {symbol} in channel {ctx.channel.id}")

# Command for remove tracking stocks
@bot.command(name='untrack')
async def untrack_stock(ctx, symbol: str):
    symbol = symbol.upper()
    if ctx.channel.id in tracked_stocks and symbol in tracked_stocks[ctx.channel.id]:
        tracked_stocks[ctx.channel.id].remove(symbol)
        await ctx.send(f"หยุดติดตามหุ้น **{symbol}** แล้วในช่องนี้")
        logging.info(f"Untracked {symbol} in channel {ctx.channel.id}")
        if not tracked_stocks[ctx.channel.id]: # ถ้าไม่มีหุ้นเหลือแล้ว ให้ลบ entry ของ channel นั้นทิ้ง
            del tracked_stocks[ctx.channel.id]
    else:
        await ctx.send(f"ไม่พบหุ้น **{symbol}** ที่ติดตามอยู่ในช่องนี้")

# Command for check list tracking stocks
@bot.command(name='liststocks')
async def list_stocks(ctx):
    if ctx.channel.id in tracked_stocks and tracked_stocks[ctx.channel.id]:
        stocks = ", ".join(sorted(list(tracked_stocks[ctx.channel.id])))
        await ctx.send(f"หุ้นที่ติดตามอยู่ในช่องนี้: **{stocks}**")
    else:
        await ctx.send("ยังไม่มีหุ้นที่ติดตามอยู่ในช่องนี้")

# Command for get stocks price
@bot.command(name='quote')
async def get_instant_quote(ctx, symbol: str):
    symbol = symbol.upper()
    
    await ctx.send(f"กำลังดึงข้อมูลหุ้น **{symbol}**...")
    quote_data = stock_data_api.get_stock_data(symbol) 

    if quote_data:
        price = quote_data['current_price']
        change = quote_data['change']
        percent_change = quote_data['percent_change']
        emoji = "🟢" if change > 0 else "🔴" if change < 0 else "⚪"
        
        message = (
            f"📊 **{quote_data['symbol']}** (ข้อมูลล่าสุด): "
            f"ราคาปัจจุบัน: **${price:.2f}** "
            f"{emoji} ({change:+.2f}, {percent_change:+.2f}%)"
        )
        await ctx.send(message)
    else:
        await ctx.send(f"⚠️ ไม่สามารถดึงข้อมูลหุ้น **{symbol}** ได้ในขณะนี้ (อาจเป็นเพราะ Rate Limit หรือข้อมูลไม่ถูกต้อง)")


# Function to send stock updates
async def send_stock_updates():
    logging.info(f"Initiating stock update at {datetime.now()}")
    symbols_to_check = set()
    for channel_symbols in tracked_stocks.values():
        symbols_to_check.update(channel_symbols)

    if not symbols_to_check:
        logging.info("No stocks to track for price updates.")
        return

    for symbol in symbols_to_check:
        quote_data = stock_data_api.get_stock_data(symbol)
        if quote_data:
            price = quote_data['current_price']
            change = quote_data['change']
            percent_change = quote_data['percent_change']
            emoji = "🟢" if change > 0 else "🔴" if change < 0 else "⚪"
            
            message = (
                f"📊 **{quote_data['symbol']}** "
                f"ราคาปัจจุบัน: **${price:.2f}** "
                f"{emoji} ({change:+.2f}, {percent_change:+.2f}%)"
            )
            # Send message to all channels that track this stock
            for channel_id, symbols_in_channel in tracked_stocks.items():
                if symbol in symbols_in_channel:
                    channel = bot.get_channel(channel_id)
                    if channel:
                        try:
                            await channel.send(message)
                            logging.info(f"Sent price update for {symbol} to channel {channel_id}")
                        except discord.Forbidden:
                            logging.warning(f"Bot doesn't have permission to send messages in channel {channel_id}")
        else:
            logging.warning(f"Could not retrieve price data for {symbol}.")
        
        await asyncio.sleep(1) # Wait 1 second between requests to avoid hitting the API rate limit

# Notify at specific times

# Notify 06:00 AM (US Market Close)
@tasks.loop(time=time(6, 0))
async def daily_stock_update_morning():
    logging.info("Running daily_stock_update_morning task at 06:00 THA.")
    await send_stock_updates()

# Notify 09:00 AM (US Market Open)
@tasks.loop(time=time(21, 0))
async def daily_stock_update_open():
    logging.info("Running daily_stock_update_open task at 21:00 THA (US Market Open).")
    await send_stock_updates()

# Notify 00:00 AM (Midnight)
@tasks.loop(time=time(0, 0))
async def daily_stock_update_midnight():
    logging.info("Running daily_stock_update_midnight task at 00:00 THA.")
    await send_stock_updates()

# Task for checking news updates
@tasks.loop(minutes=30) # Check every 30 minutes
async def check_news_task():
    logging.info(f"Checking news at {datetime.now()}")
    symbols_to_check = set()
    for channel_symbols in tracked_stocks.values():
        symbols_to_check.update(channel_symbols)

    if not symbols_to_check:
        logging.info("No stocks to track for news updates.")
        return

    for symbol in symbols_to_check:
        # Get news articles for the stock symbol
        news_articles = stock_data_api.get_company_news(symbol, days_ago=2) 
        
        if news_articles:
            # Check if there are new articles
            for article in news_articles:
                # Finnhub news ID is 'id' field
                news_id = str(article['id']) # Convert to string for consistency
                
                # Check if the news has already been sent to any channel
                is_sent_to_any_channel = False
                for channel_id, symbols_in_channel in tracked_stocks.items():
                    if symbol in symbols_in_channel:
                        if await news_storage.is_news_sent(news_id, channel_id):
                            is_sent_to_any_channel = True
                            break
                
                if not is_sent_to_any_channel:
                    news_message = (
                        f"📰 **Latest News for {symbol}**\n"
                        f"> **{article['headline']}**\n"
                        f"> Summary: {article['summary'] if article['summary'] else 'No summary available.'}\n"
                        f"> Source: {article['source']}\n"
                        f"> Read more: <{article['url']}>"
                    )
                    
                    # Send the news message to all channels that track this stock
                    for channel_id, symbols_in_channel in tracked_stocks.items():
                        if symbol in symbols_in_channel:
                            channel = bot.get_channel(channel_id)
                            if channel:
                                try:
                                    await channel.send(news_message)
                                    # Add the news ID to the database to mark it as sent
                                    await news_storage.add_sent_news(news_id, symbol, channel_id)
                                    logging.info(f"Sent news (ID: {news_id}) for {symbol} to channel {channel_id}")
                                except discord.Forbidden:
                                    logging.warning(f"Bot doesn't have permission to send messages in channel {channel_id}")
                else:
                    logging.info(f"News (ID: {news_id}) for {symbol} already sent to a tracking channel.")
        else:
            logging.info(f"No new news found for {symbol}.")
        
        # Rate limit to avoid hitting the API too hard
        await asyncio.sleep(2) # Wait 2 seconds between requests to avoid hitting the API rate limit

# Task for cleaning old news
@tasks.loop(hours=24) # Run once a day
async def clean_old_news_task():
    logging.info("Starting clean_old_news_task...")
    await news_storage.clean_old_news(days_to_keep=7) # Keep news for 7 days
    logging.info("Finished clean_old_news_task.")


# Run the bot
if not config.DISCORD_BOT_TOKEN or config.DISCORD_BOT_TOKEN == "YOUR_DISCORD_BOT_TOKEN":
    logging.error("Error: DISCORD_BOT_TOKEN not set in config.py.")
    logging.error("Please set your Discord bot token in config.py.")
else:
    bot.run(config.DISCORD_BOT_TOKEN)