import os
import discord
from discord.ext import commands
from flask import Flask, request
from threading import Thread
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import asyncio
import json
import logging

# --- Keep-alive web server and webhook receiver ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    print("📥 Webhook received:", data)

    timestamp = data.get('timestamp', '')
    game = data.get('game', '').strip()
    branch = data.get('branch', '').strip()
    name = data.get('name', '').strip()
    work = data.get('work', '').strip()

    if '[แจ้ง]' in work:
        print("🆕 '[แจ้ง]' found in work, sending new message.")
        cleaned_work = work.replace('[แจ้ง]', '').strip()
        message = f"📌 `{timestamp}` | `{game}` | `{branch}`\n👤 {name}\n🛠️ {cleaned_work}"

        channel = bot.get_channel(DISCORD_CHANNEL_ID)
        if channel:
            future = asyncio.run_coroutine_threadsafe(channel.send(message), bot.loop)
            try:
                sent_msg = future.result(timeout=10)
                print(f"✅ Message sent with ID: {sent_msg.id}")

                # Log in Sheet3
                sheet3 = sheet.worksheet("Sheet3")
                sheet3.append_row([str(sent_msg.id), game.lower(), branch.lower(), cleaned_work.lower()])
                print("📝 Message ID logged to Sheet3.")
            except Exception as e:
                print(f"❌ Failed to send or log message: {e}")
        else:
            print("❌ Discord channel not found.")
    else:
        print("✏️ '[แจ้ง]' not found, attempting to edit existing message.")
        cleaned_work = work.replace('[แจ้ง]', '').strip()

        sheet3 = sheet.worksheet("Sheet3")
        records = sheet3.get_all_records()
        target_row = None
        for idx, row in enumerate(reversed(records)):
            print(f"🔍 Checking row: {row}")
            if row['game'].strip().lower() == game.lower() and \
               row['branch'].strip().lower() == branch.lower() and \
               row['work'].strip().lower() == cleaned_work.lower():
                target_row = row
                break

        if target_row:
            message_id = int(target_row['message_id'])
            print(f"✏️ Editing message ID: {message_id}")

            channel = bot.get_channel(DISCORD_CHANNEL_ID)
            if channel:
                try:
                    future = asyncio.run_coroutine_threadsafe(channel.fetch_message(message_id), bot.loop)
                    old_msg = future.result(timeout=10)
                    if old_msg:
                        new_content = f"~~{old_msg.content}~~\n⭐️ {name}"
                        future_edit = asyncio.run_coroutine_threadsafe(old_msg.edit(content=new_content), bot.loop)
                        future_edit.result(timeout=10)
                        print("✅ Message edited successfully.")
                    else:
                        print("❌ Could not fetch the old message.")
                except Exception as e:
                    print(f"❌ Error editing message: {e}")
        else:
            print("⚠️ No matching message found in Sheet3.")

    return jsonify({'status': 'ok'})


def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    Thread(target=run).start()


# --- Google Sheets setup ---
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
creds_json_str = os.getenv("GOOGLE_CREDENTIALS_JSON")
if not creds_json_str:
    raise Exception("Environment variable GOOGLE_CREDENTIALS_JSON not set!")
creds_dict = json.loads(creds_json_str)
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sh = client.open("NFC")
sheet = sh.worksheet("Sheet1")


# --- Discord bot setup ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)
bot.remove_command('help')


def format_work_line(work, count):
    return f"✅{work} ({count})"

@bot.command()
async def ping(ctx):
    await ctx.send('Pong!')

@bot.command(name="most")
async def most_command(ctx, date_range: str = None, top_x: str = "10"):
    if not date_range:
        await ctx.send("Please provide date range and number. Ex: !most 25May2025-26May2025 10")
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


@bot.command()
async def w(ctx, *args):
    sheet = sh.worksheet('Sheet1')  # Your sheet1 reference
    data = sheet.get_all_records()

    def parse_date(date_str):
        try:
            return datetime.strptime(date_str.capitalize(), '%d%b%Y').date()
        except ValueError:
            try:
                return datetime.strptime(date_str.upper(), '%d%b%Y').date()
            except ValueError:
                return None

    if len(args) == 0:
        query_date = datetime.today().date()
        query_name = 'all'
    elif len(args) == 1:
        arg = args[0].lower()
        if arg == 'all':
            query_date = datetime.today().date()
            query_name = 'all'
        elif arg == 'yesterday':
            query_date = (datetime.today() - timedelta(days=1)).date()
            query_name = 'all'
        else:
            query_date = datetime.today().date()
            query_name = args[0]
    elif len(args) == 2:
        date_arg = args[0].lower()
        name_arg = args[1]
        if date_arg == 'yesterday':
            query_date = (datetime.today() - timedelta(days=1)).date()
        else:
            query_date = parse_date(date_arg)
            if query_date is None:
                await ctx.send("❌ Invalid date format. Use ddMMMyyyy, e.g. 05Jun2025.")
                return
        query_name = name_arg
    else:
        await ctx.send("❌ Invalid command format.")
        return

    # Filter rows by date and name
    filtered_rows = []
    for row in data:
        try:
            ts_date = datetime.strptime(row['Timestamps'], '%m/%d/%Y %H:%M:%S').date()
        except Exception:
            continue

        if ts_date == query_date:
            if query_name.lower() == 'all' or row['Name'].lower() == query_name.lower():
                filtered_rows.append(row)

    if not filtered_rows:
        await ctx.send(f"❌ ไม่พบข้อมูลงานของ `{query_name}` ในวันที่ `{query_date.strftime('%d/%m/%Y')}`")
        return

    # Group by work -> list of games
    from collections import defaultdict

    work_groups = defaultdict(list)
    for row in filtered_rows:
        work = row['Work'].strip() or "สอนเกม"
        game = row.get('Game', '').strip()
        work_groups[work].append(game)

    # Prepare output message
    header = f"📋 งานของ {query_name} วันที่ {query_date.strftime('%d/%m/%Y')}"
    output_lines = [header]

    # Sort works so "สอนเกม" is first if exists
    sorted_works = sorted(work_groups.keys(), key=lambda w: (w != "สอนเกม", w))

    for work in sorted_works:
        games = work_groups[work]
        output_lines.append(f"✅{work} ({len(games)})")
        for game in games:
            output_lines.append(game)

    await ctx.send("\n".join(output_lines))



# Start the web server for UptimeRobot and webhook
keep_alive()

logging.basicConfig(level=logging.INFO)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
bot.run(TOKEN)
