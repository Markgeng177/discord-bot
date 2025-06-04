import os
import discord
from discord.ext import commands
from flask import Flask, request
from threading import Thread
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from collections import defaultdict, OrderedDict
import asyncio
import json
import re

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

# Load credentials JSON from environment variable and parse it
creds_json_str = os.getenv("GOOGLE_CREDENTIALS_JSON")
if not creds_json_str:
    raise Exception("Environment variable GOOGLE_CREDENTIALS_JSON not set!")

creds_dict = json.loads(creds_json_str)
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
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





@bot.command(name="most")
async def most_command(ctx, date_range: str = None, top_x: str = "10"):
    if not date_range:
        await ctx.send(
            "Please provide date range and number. Ex: !most 25May2025-26May2025 10"
        )
        return

    try:
        from_str, to_str = date_range.split("-")
        start_date = datetime.strptime(from_str.strip(), "%d%b%Y")
        end_date = datetime.strptime(to_str.strip(), "%d%b%Y")
    except ValueError:
        await ctx.send("❌ Invalid date format. Use this format: `25May2025-26May2025`")
        return

    data = sheet.get_all_records()
    game_counts = {}

    for row in data:
        try:
            sheet_year = int(row['Year'])
            if sheet_year < 100:
                sheet_year += 2000
            sheet_date = int(row['Date'])
            sheet_month = row['Month'].strip()
            sheet_date_obj = datetime.strptime(f"{sheet_date} {sheet_month} {sheet_year}", "%d %B %Y")
        except:
            continue

        if start_date <= sheet_date_obj <= end_date:
            game = row['Game'].strip()
            if game:
                game_counts[game] = game_counts.get(game, 0) + 1

    top_count = int(top_x)
    sorted_games = sorted(game_counts.items(), key=lambda x: x[1], reverse=True)[:top_count]

    if not sorted_games:
        await ctx.send("No games found in that date range.")
        return

    response_lines = [f"📊 Top {top_count} most frequent games from {start_date.strftime('%d %b %Y')} to {end_date.strftime('%d %b %Y')}:"]
    for game, count in sorted_games:
        response_lines.append(f"{game} ({count})")

    await ctx.send("\n".join(response_lines))


@bot.command(name="help")
async def help_command(ctx):
    help_text = (
        "Help command:\n"
        "`!w <name>` - Show today's work for a name.\n"
        "`!w y <name>` - Show yesterday's work for a name.\n"
        "`!w <ddMMMyyyy> <name>` - Show work for a name on a specific date.\n"
        "`!w all` - Show all work today.\n"
        "`!most <startdate-enddate> <number>` - Show top games in the date range.\n"
        "`!ping` - Ping the bot."
    )
    await ctx.send(help_text)


keep_alive()

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} - {bot.user.id}')

from datetime import datetime
from collections import defaultdict, OrderedDict

@bot.command()
async def w(ctx, *, arg):
    sheet = client.open('NFC').worksheet('Sheet1')
    data = sheet.get_all_values()[1:]  # skip header

    parts = arg.strip().split()

    # Determine date and whether it's for "all"
    try:
        if len(parts) > 1 and re.match(r"\d{1,2}[a-zA-Z]{3,9}\d{4}", parts[0]):
            date_part = parts[0]
            name_query = " ".join(parts[1:])
            date_obj = datetime.strptime(date_part, "%d%b%Y").date()
        elif parts[0].lower() == 'y':
            name_query = " ".join(parts[1:])
            date_obj = datetime.now().date() - timedelta(days=1)
        elif parts[0].lower() == 'all':
            if len(parts) == 1:
                date_obj = datetime.now().date()
                name_query = "all"
            elif parts[1].lower() == 'y':
                date_obj = datetime.now().date() - timedelta(days=1)
                name_query = "all"
            elif re.match(r"\d{1,2}[a-zA-Z]{3,9}\d{4}", parts[1]):
                date_obj = datetime.strptime(parts[1], "%d%b%Y").date()
                name_query = "all"
            else:
                await ctx.send("❌ รูปแบบไม่ถูกต้อง เช่น `!w all y` หรือ `!w all 27May2025`")
                return
        else:
            name_query = arg.strip()
            date_obj = datetime.now().date()
    except Exception as e:
        await ctx.send(f"❌ ไม่สามารถแปลงวันที่จาก `{parts[0]}` ได้ กรุณาใช้รูปแบบ 27May2025")
        return

    category_order = [
        "สอนเกม", "ซ่อมซอง", "ซ่อมห่อปก", "เรียนเกม",
        "[แจ้ง] ซ่อมซอง", "[แจ้ง] ซ่อมปก"
    ]

    work_dict = defaultdict(list)

    for row in data:
        try:
            timestamp_str = row[0].strip()
            game = row[1].strip()
            name = row[3].strip()
            work = row[4].strip()

            timestamp = datetime.strptime(timestamp_str, '%m/%d/%Y %H:%M:%S')
            if timestamp.date() != date_obj:
                continue

            if name_query != "all" and name != name_query:
                continue

            category = "สอนเกม" if not work else work
            work_dict[category].append(game)
        except Exception as e:
            print("Row error:", row, e)
            continue

    if not work_dict:
        label = "ทั้งหมด" if name_query == "all" else name_query
        await ctx.send(f"ไม่พบงานของ {label} วันที่ {date_obj.strftime('%d/%m/%Y')}.")
        return

    sorted_work = OrderedDict()
    for cat in category_order:
        if cat in work_dict:
            sorted_work[cat] = work_dict[cat]
    for cat in work_dict:
        if cat not in sorted_work:
            sorted_work[cat] = work_dict[cat]

    label = "ทั้งหมด" if name_query == "all" else name_query
    response = f"📋 งานของ {label} วันที่ {date_obj.strftime('%d/%m/%Y')}\n"
    for cat, games in sorted_work.items():
        response += f"✅{cat} ({len(games)})\n"
        response += "\n".join(games) + "\n"

    await ctx.send(response)



bot.run(os.getenv("DISCORD_BOT_TOKEN"))
