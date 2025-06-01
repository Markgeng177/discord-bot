import os
import discord
from discord.ext import commands
from flask import Flask, request
from threading import Thread
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import asyncio

# --- Keep-alive web server for UptimeRobot and Webhook Receiver ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    try:
        data = request.json
        if not data or 'work' not in data:
            return '', 200

        timestamp = data.get('timestamp', 'N/A').strip()
        game = data.get('game', 'N/A').strip()
        branch = data.get('branch', 'N/A').strip()
        name = data.get('name', 'N/A').strip()
        work = data.get('work', '').strip()

        async def send_new_message():
            await bot.wait_until_ready()
            channel = bot.get_channel(1376569123873493042)
            if not channel:
                print("Channel not found")
                return
            msg_content = (f"📢 แจ้งเตือนจาก Google Form\n"
                           f"Timestamps: {timestamp}\n"
                           f"Game: {game}\n"
                           f"Branch: {branch}\n"
                           f"name: {name}\n"
                           f"Work: {work}")
            sent_msg = await channel.send(msg_content)
            print(f"Sent new message ID: {sent_msg.id}")

        async def find_and_edit_message_by_game_branch_and_work():
            await bot.wait_until_ready()
            channel = bot.get_channel(1376569123873493042)
            if not channel:
                print("Channel not found")
                return False

            async for msg in channel.history(limit=100):
                if "📢 แจ้งเตือนจาก Google Form" not in msg.content:
                    continue

                lines = msg.content.splitlines()
                msg_game = ""
                msg_branch = ""
                for line in lines:
                    line = line.strip()
                    if line.lower().startswith("game:"):
                        msg_game = line.split(":", 1)[1].strip().lower()
                    elif line.lower().startswith("branch:"):
                        msg_branch = line.split(":", 1)[1].strip().lower()

                if msg_game == game.lower().strip() and msg_branch == branch.lower().strip():
                    updated = f"~~{msg.content}~~\n⭐️{name}"
                    await msg.edit(content=updated)
                    print(f"Edited message ID: {msg.id}")
                    return True

            print("No matching message found to edit.")
            return False

        async def process_message():
            if not work.strip():
                print("Empty work; ignoring")
                return

            if '[แจ้ง]' in work:
                await send_new_message()
            else:
                edited = await find_and_edit_message_by_game_branch_and_work()
                if not edited:
                    print("No matching message found to edit.")

        asyncio.run_coroutine_threadsafe(process_message(), bot.loop)

        return '', 200

    except Exception as e:
        print(f"Webhook error: {e}")
        return '', 500


def run():
    app.run(host='0.0.0.0', port=8080)


def keep_alive():
    Thread(target=run).start()


# --- Google Sheets setup ---
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
creds = ServiceAccountCredentials.from_json_keyfile_name(
    "credentials.json", scope)
client = gspread.authorize(creds)
sheet = client.open("NFC").worksheet("Sheet1")

# --- Discord bot setup ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)
bot.remove_command('help')


def format_work_line(work, count):
    return f"✅{work} ({count})"


async def send_work_for_name(ctx, name: str, target_date: datetime):
    data = sheet.get_all_records()
    today_date = target_date.day
    today_month = target_date.strftime("%B")
    today_year = target_date.year

    filtered = []
    for row in data:
        try:
            sheet_year = int(row['Year'])
            if sheet_year < 100:
                sheet_year += 2000
            sheet_date = int(row['Date'])
            sheet_month = row['Month'].strip()
        except:
            continue

        if (row['Name'].strip().lower() == name.strip().lower()
                and sheet_date == today_date and sheet_month == today_month
                and sheet_year == today_year):
            filtered.append(row)

    if not filtered:
        return None

    work_order = []
    work_to_games = {}

    for row in filtered:
        work_val = str(row['Work']).strip()
        if work_val == "" or work_val.lower() == "none":
            work_val = "สอนเกม"
        if work_val not in work_to_games:
            work_order.append(work_val)
            work_to_games[work_val] = []
        work_to_games[work_val].append(row['Game'])

    if "สอนเกม" in work_order:
        work_order.remove("สอนเกม")
        work_order.insert(0, "สอนเกม")

    response_lines = [f"⭐️{name.strip()}"]
    for work in work_order:
        count = len(work_to_games[work])
        response_lines.append(format_work_line(work, count))
        response_lines.extend(work_to_games[work])

    return "\n".join(response_lines)


async def send_work_for_all(ctx, target_date: datetime):
    data = sheet.get_all_records()
    today_date = target_date.day
    today_month = target_date.strftime("%B")
    today_year = target_date.year

    per_user = {}
    all_work_order = []
    all_work_to_games = {}

    for row in data:
        try:
            sheet_year = int(row['Year'])
            if sheet_year < 100:
                sheet_year += 2000
            sheet_date = int(row['Date'])
            sheet_month = row['Month'].strip()
        except:
            continue

        if (sheet_date == today_date and sheet_month == today_month
                and sheet_year == today_year):
            name = row['Name'].strip()
            work_val = str(row['Work']).strip()
            if work_val == "" or work_val.lower() == "none":
                work_val = "สอนเกม"
            if name not in per_user:
                per_user[name] = {}
            if work_val not in per_user[name]:
                per_user[name][work_val] = []
            per_user[name][work_val].append(row['Game'])

            if work_val not in all_work_to_games:
                all_work_order.append(work_val)
                all_work_to_games[work_val] = []
            all_work_to_games[work_val].append(row['Game'])

    if not all_work_order:
        await ctx.send("No work found for all names on this date.")
        return

    if "สอนเกม" in all_work_order:
        all_work_order.remove("สอนเกม")
        all_work_order.insert(0, "สอนเกม")

    response_lines = ["⭐️all"]
    for work in all_work_order:
        count = len(all_work_to_games[work])
        response_lines.append(format_work_line(work, count))
        response_lines.extend(all_work_to_games[work])

    for name, works in per_user.items():
        response_lines.append(f"⭐️{name}")
        work_keys = list(works.keys())
        if "สอนเกม" in work_keys:
            work_keys.remove("สอนเกม")
            work_keys.insert(0, "สอนเกม")
        for work in work_keys:
            count = len(works[work])
            response_lines.append(format_work_line(work, count))
            response_lines.extend(works[work])

    await ctx.send("\n".join(response_lines))


@bot.command()
async def ping(ctx):
    await ctx.send('Pong!')


@bot.command(name='w')
async def work_command(ctx, *args):
    now = datetime.now()

    def parse_date_str(dstr):
        try:
            return datetime.strptime(dstr, "%d%b%Y")
        except ValueError:
            return None

    if len(args) == 0:
        await ctx.send("Please provide a name, date, or 'all'.")
        return

    first = args[0].lower()

    if first == "all":
        await send_work_for_all(ctx, now)
        return
    elif first == "y" and len(args) > 1 and args[1].lower() == "all":
        yesterday = now - timedelta(days=1)
        await send_work_for_all(ctx, yesterday)
        return
    elif parse_date_str(first) and len(args) > 1 and args[1].lower() == "all":
        target_date = parse_date_str(first)
        await send_work_for_all(ctx, target_date)
        return

    if first == "y" and len(args) > 1:
        name = " ".join(args[1:])
        yesterday = now - timedelta(days=1)
        resp = await send_work_for_name(ctx, name, yesterday)
        await ctx.send(
            resp
            or f"No work found for {name} on {yesterday.strftime('%d %b %Y')}."
        )
        return

    if parse_date_str(first) and len(args) > 1:
        target_date = parse_date_str(first)
        name = " ".join(args[1:])
        resp = await send_work_for_name(ctx, name, target_date)
        await ctx.send(
            resp or
            f"No work found for {name} on {target_date.strftime('%d %b %Y')}.")
        return

    name = " ".join(args)
    resp = await send_work_for_name(ctx, name, now)
    await ctx.send(resp or f"No work found for {name} today.")


@bot.command(name="most")
async def most_command(ctx, date_range: str = None, top_x: str = "10"):
    if not date_range:
        await ctx.send(
            "Please provide date range and number. Ex: !most 25may2025-26may2025 10"
        )
        return

    try:
    from_str, to_str = date_range.split("-")
    start_date = datetime.strptime(from_str.strip(), "%d%b%Y")
    end_date = datetime.strptime(to_str.strip(), "%d%b%Y")
except ValueError:
    await message.channel.send("❌ Invalid date format. Use this format: `25May2025-26May2025`")
    return

