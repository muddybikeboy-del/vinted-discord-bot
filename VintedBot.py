import discord
import asyncio
import re
import os
from statistics import mean
from playwright.async_api import async_playwright

# 🔐 Get token from environment variable
TOKEN = os.getenv("TOKEN")

if not TOKEN:
    raise ValueError("No TOKEN found. Set environment variable TOKEN.")

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

DEAL_THRESHOLD = 0.30
MAX_RESULTS = 20


@client.event
async def on_ready():
    print(f"Logged in as {client.user}")


@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.content.startswith("!scan"):
        search_term = message.content.replace("!scan ", "").strip()

        if not search_term:
            await message.channel.send("Use: `!scan item name`")
            return

        await message.channel.send(f"Scanning for **{search_term}**... ⏳")

        search_url = f"https://www.vinted.co.uk/catalog?search_text={search_term.replace(' ','+')}"

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
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

            if not prices:
                await message.channel.send("No items found.")
                await browser.close()
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
                await message.channel.send(f"🔥 Top {len(top_deals)} Deals 🔥")

                for deal in top_deals:
                    msg = (
                        f"**{deal['title']}**\n"
                        f"Buy: £{deal['price']:.2f}\n"
                        f"Market Avg: £{avg_price:.2f}\n"
                        f"Estimated Profit: £{deal['profit']:.2f}\n"
                        f"{deal['link']}"
                    )

                    await message.channel.send(msg)
                    await asyncio.sleep(0.5)

            await browser.close()


client.run(TOKEN)
