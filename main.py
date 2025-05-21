# main.py

import discord
from discord.ext import commands, tasks
from datetime import datetime
import asyncio
import logging

# นำเข้า API Key และ Token
import config
# นำเข้าฟังก์ชันจากไฟล์ที่เราสร้าง
import stock_data_api
import news_storage

# ตั้งค่า Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ตั้งค่า Bot
intents = discord.Intents.default()
intents.message_content = True
intents.members = True # จำเป็นสำหรับ Privileged Intents
intents.presences = True # จำเป็นสำหรับ Privileged Intents

bot = commands.Bot(command_prefix='!', intents=intents)

# เก็บหุ้นที่ผู้ใช้สนใจ
# key: channel_id, value: set of symbols (ใช้ set เพื่อป้องกันหุ้นซ้ำ)
tracked_stocks = {}

@bot.event
async def on_ready():
    logging.info(f'{bot.user} ได้เชื่อมต่อกับ Discord เรียบร้อยแล้ว!')
    await news_storage.init_db() # เริ่มต้นฐานข้อมูลข่าวสาร
    logging.info("Database initialized.")
    
    # เริ่มต้น task สำหรับแจ้งเตือนหุ้นและข่าวสาร
    check_stock_prices_task.start()
    check_news_task.start()
    clean_old_news_task.start() # เริ่ม task ทำความสะอาดฐานข้อมูล

# คำสั่งสำหรับเพิ่มหุ้นที่ต้องการติดตาม
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

# คำสั่งสำหรับหยุดติดตามหุ้น
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

# คำสั่งสำหรับดูหุ้นที่กำลังติดตาม
@bot.command(name='liststocks')
async def list_stocks(ctx):
    if ctx.channel.id in tracked_stocks and tracked_stocks[ctx.channel.id]:
        stocks = ", ".join(sorted(list(tracked_stocks[ctx.channel.id])))
        await ctx.send(f"หุ้นที่ติดตามอยู่ในช่องนี้: **{stocks}**")
    else:
        await ctx.send("ยังไม่มีหุ้นที่ติดตามอยู่ในช่องนี้")

# คำสั่งสำหรับตรวจสอบราคาหุ้นทันที (ระวัง Rate Limit)
@bot.command(name='quote')
async def get_instant_quote(ctx, symbol: str):
    symbol = symbol.upper()
    
    await ctx.send(f"กำลังดึงข้อมูลหุ้น **{symbol}**...")
    quote_data = stock_data_api.get_stock_data(symbol) 

    if quote_data:
        price = quote_data['current_price']
        change = quote_data['change']
        percent_change = quote_data['percent_change']
        emoji = "⬆️" if change > 0 else "⬇️" if change < 0 else "↔️"
        
        message = (
            f"📊 **{quote_data['symbol']}** (ข้อมูลล่าสุด): "
            f"ราคาปัจจุบัน: **${price:.2f}** "
            f"{emoji} ({change:+.2f}, {percent_change:+.2f}%)"
        )
        await ctx.send(message)
    else:
        await ctx.send(f"⚠️ ไม่สามารถดึงข้อมูลหุ้น **{symbol}** ได้ในขณะนี้ (อาจเป็นเพราะ Rate Limit หรือข้อมูลไม่ถูกต้อง)")


# Task สำหรับตรวจสอบราคาหุ้น (Finnhub มี Rate Limit ค่อนข้างสูงสำหรับ Quote API)
@tasks.loop(minutes=5) # สามารถปรับได้
async def check_stock_prices_task():
    logging.info(f"Checking stock prices at {datetime.now()}")
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
            emoji = "⬆️" if change > 0 else "⬇️" if change < 0 else "↔️"
            
            message = (
                f"📊 **{quote_data['symbol']}** "
                f"ราคาปัจจุบัน: **${price:.2f}** "
                f"{emoji} ({change:+.2f}, {percent_change:+.2f}%)"
            )
            # ส่งไปยังทุกช่องที่ติดตามหุ้นตัวนี้
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
        
        # เว้นช่วงระหว่างการเรียก API เพื่อไม่ให้ชน Rate Limit (Finnhub Quote API ค่อนข้างใจกว้าง)
        await asyncio.sleep(1) # รอ 1 วินาทีต่อหุ้น 1 ตัว (ถ้ามี 10 ตัว จะใช้ 10 วินาที)


# Task สำหรับตรวจสอบข่าวสาร (Finnhub News API มี Rate Limit แยก)
@tasks.loop(minutes=30) # ตรวจสอบทุก 30 นาที (สามารถปรับได้)
async def check_news_task():
    logging.info(f"Checking news at {datetime.now()}")
    symbols_to_check = set()
    for channel_symbols in tracked_stocks.values():
        symbols_to_check.update(channel_symbols)

    if not symbols_to_check:
        logging.info("No stocks to track for news updates.")
        return

    for symbol in symbols_to_check:
        # ดึงข่าวสาร (ดึงย้อนหลัง 1-2 วัน เพื่อไม่ให้พลาดข่าวที่เพิ่งมา)
        news_articles = stock_data_api.get_company_news(symbol, days_ago=2) 
        
        if news_articles:
            # กรองและส่งข่าวที่ยังไม่เคยส่ง
            for article in news_articles:
                # Finnhub news ID เป็น 'id' field
                news_id = str(article['id']) # แปลงเป็น string เพื่อความปลอดภัยในการเก็บใน DB
                
                # ตรวจสอบว่าเคยส่งข่าวนี้ไปแล้วในช่องใดช่องหนึ่งที่ติดตามหุ้นนี้หรือไม่
                is_sent_to_any_channel = False
                for channel_id, symbols_in_channel in tracked_stocks.items():
                    if symbol in symbols_in_channel:
                        if await news_storage.is_news_sent(news_id, channel_id):
                            is_sent_to_any_channel = True
                            break
                
                if not is_sent_to_any_channel:
                    # ไม่มีการแปลภาษาไทยแล้ว จะส่งเป็นภาษาอังกฤษตามที่ API ส่งมา
                    news_message = (
                        f"📰 **Latest News for {symbol}**\n"
                        f"> **{article['headline']}**\n"
                        f"> Summary: {article['summary'] if article['summary'] else 'No summary available.'}\n"
                        f"> Source: {article['source']}\n"
                        f"> Read more: <{article['url']}>"
                    )
                    
                    # ส่งไปยังทุกช่องที่ติดตามหุ้นตัวนี้
                    for channel_id, symbols_in_channel in tracked_stocks.items():
                        if symbol in symbols_in_channel:
                            channel = bot.get_channel(channel_id)
                            if channel:
                                try:
                                    await channel.send(news_message)
                                    # เพิ่ม ID ข่าวลงในฐานข้อมูลว่าถูกส่งไปแล้วในช่องนี้
                                    await news_storage.add_sent_news(news_id, symbol, channel_id)
                                    logging.info(f"Sent news (ID: {news_id}) for {symbol} to channel {channel_id}")
                                except discord.Forbidden:
                                    logging.warning(f"Bot doesn't have permission to send messages in channel {channel_id}")
                else:
                    logging.info(f"News (ID: {news_id}) for {symbol} already sent to a tracking channel.")
        else:
            logging.info(f"No new news found for {symbol}.")
        
        # เว้นช่วงระหว่างการเรียก API ข่าว (Finnhub News API limit: 30 calls/minute)
        await asyncio.sleep(2) # รอ 2 วินาทีต่อหุ้น 1 ตัว (ถ้ามี 10 ตัว จะใช้ 20 วินาที)

# Task สำหรับทำความสะอาดฐานข้อมูลข่าวสารเก่าๆ
@tasks.loop(hours=24) # รันทุก 24 ชั่วโมง
async def clean_old_news_task():
    logging.info("Starting clean_old_news_task...")
    await news_storage.clean_old_news(days_to_keep=7) # เก็บข่าวไว้ 7 วัน
    logging.info("Finished clean_old_news_task.")


# รันบอท
if not config.DISCORD_BOT_TOKEN or config.DISCORD_BOT_TOKEN == "YOUR_DISCORD_BOT_TOKEN":
    logging.error("Error: DISCORD_BOT_TOKEN not set in config.py.")
    logging.error("Please set your Discord bot token in config.py.")
else:
    bot.run(config.DISCORD_BOT_TOKEN)