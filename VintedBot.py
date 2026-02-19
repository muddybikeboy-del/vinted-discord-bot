import discord
import asyncio
import re
import os
import time
from statistics import mean
from playwright.async_api import async_playwright

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

DEAL_THRESHOLD = 0.30
MAX_RESULTS = 20
INACTIVITY_LIMIT = 600  # 10 minutes

browser_instance = None
last_used = time.time()


async def get_browser():
    global browser_instance
    if browser_instance is None:
        p = await async_playwright().start()
        browser_instance = await p.chromium.launch(headless=True)
    return browser_instance


async def close_browser_if_idle():
    global browser_instance
    while True:
        await asyncio.sleep(60)
        if browser_instance and (time.time() - last_used > INACTIVITY_LIMIT):
            await browser_instance.close()
            browser_instance = None
            print("Browser closed due to inactivity.")


@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    client.loop.create_task(close_browser_if_idle())


@client.event
async def on_message(message):
    global last_used

    if message.author == client.user:
        return

    if message.content.startswith("!scan"):
        last_used = time.time()

        search_term = message.content.replace("!scan ", "").strip()

        if not search_term:
            await message.channel.send("Use: `!scan item name`")
            return

        await message.channel.send(f"Scanning for **{search_term}**... ⏳")

        browser = await get_browser()
        page = await browser.new_page()

        search_url = f"https://www.vinted.co.uk/catalog?search_text={search_term.replace(' ','+')}"
        await page.goto(search_url)
        await asyncio.sleep(5)

        cards = await page.query_selector_all("div.feed-grid__item")

        prices = []
        listings = []

        for card in cards:
            try:
                text = await card.inner_text()
                price_match = re.search(r"£(\d+(\.\d{1,2})?)", text)
                if not price_match:
                    continue

                price = float(price_match.group(1))
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                title = lines[0] if lines else "Unknown"

                link_element = await card.query_selector("a[href*='/items/']")
                if not link_element:
                    continue

                link = await link_element.get_attribute("href")
                if link.startswith("/"):
                    link = "https://www.vinted.co.uk" + link

                prices.append(price)
                listings.append({
                    "title": title,
                    "price": price,
                    "link": link
                })

            except:
                continue

        await page.close()

        if not prices:
            await message.channel.send("No items found.")
            return

        avg_price = mean(prices)

        deals = []
        for item in listings:
            if item["price"] < avg_price * (1 - DEAL_THRESHOLD):
                profit = avg_price - item["price"]
                deals.append({
                    "title": item["title"],
                    "price": item["price"],
                    "profit": profit,
                    "link": item["link"]
                })

        deals.sort(key=lambda x: x["profit"], reverse=True)
        top_deals = deals[:MAX_RESULTS]

        if not top_deals:
            await message.channel.send("No undervalued deals found.")
        else:
            for deal in top_deals:
                msg = (
                    f"**{deal['title']}**\n"
                    f"Buy: £{deal['price']:.2f}\n"
                    f"Market Avg: £{avg_price:.2f}\n"
                    f"Profit: £{deal['profit']:.2f}\n"
                    f"{deal['link']}"
                )
                await message.channel.send(msg)
                await asyncio.sleep(0.4)


client.run(TOKEN)
