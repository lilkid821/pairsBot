import os
import logging
import threading
import traceback
import random
from datetime import datetime
from functools import wraps

# Third-party imports
from flask import Flask, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest

# Optional: Load .env file for local development
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Flask App for Render Health Checks ---
app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({
        'status': 'online',
        'bot': 'Forex Pairs Bot',
        'mode': 'polling',
        'timestamp': datetime.now().isoformat()
    })

@app.route('/health')
def health():
    return jsonify({'status': 'healthy'}), 200

def run_flask():
    """Run Flask app in a separate thread"""
    port = int(os.getenv('PORT', 10000))
    logger.info(f"Starting Flask server on port {port}")
    # use_reloader=False is crucial when running in a thread
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# --- Data & Config ---

FOREX_PAIRS = {
    'Major': [
        'EUR/USD', 'GBP/USD', 'USD/JPY', 'USD/CHF',
        'AUD/USD', 'USD/CAD', 'NZD/USD'
    ],
    'Minor': [
        'EUR/GBP', 'EUR/AUD', 'EUR/CAD', 'EUR/JPY',
        'GBP/JPY', 'GBP/AUD', 'AUD/JPY', 'AUD/NZD'
    ],
    'Exotic': [
        'USD/TRY', 'USD/ZAR', 'USD/MXN', 'USD/SGD',
        'EUR/TRY', 'GBP/ZAR', 'USD/THB', 'USD/HKD'
    ]
}

AUTHORIZED_USERS = set()

# --- Decorators ---

def authorized_only(func):
    """Decorator to restrict access to authorized users"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_user:
            return
            
        user_id = update.effective_user.id
        username = update.effective_user.username or "Unknown"
        
        # Check if user is authorized (empty set means all users allowed)
        if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
            logger.warning(f"Unauthorized access attempt by {username} (ID: {user_id})")
            await update.message.reply_text(
                "⛔ <b>Access Denied</b>\n\n"
                "You are not authorized to use this bot.\n"
                "Please contact the administrator.",
                parse_mode=ParseMode.HTML
            )
            return
        
        return await func(update, context)
    return wrapper

def rate_limit(max_calls: int = 5, period: int = 60):
    """Rate limiting decorator"""
    calls = {}
    
    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            if not update.effective_user:
                return await func(update, context)

            user_id = update.effective_user.id
            current_time = datetime.now().timestamp()
            
            if user_id not in calls:
                calls[user_id] = []
            
            # Remove old calls
            calls[user_id] = [t for t in calls[user_id] if current_time - t < period]
            
            if len(calls[user_id]) >= max_calls:
                await update.message.reply_text(
                    "⏳ Rate limit exceeded. Please wait before trying again."
                )
                return
            
            calls[user_id].append(current_time)
            return await func(update, context)
        return wrapper
    return decorator

# --- Command Handlers ---

@authorized_only
@rate_limit(max_calls=10, period=60)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    # Using HTML is safer for names with underscores
    welcome_message = (
        f"👋 <b>Welcome to Forex Pairs Bot, {user.first_name}!</b>\n\n"
        "🌍 <b>Available Commands:</b>\n"
        "• /start - Show this welcome message\n"
        "• /pairs - View all forex pairs by category\n"
        "• /major - Get major currency pairs\n"
        "• /minor - Get minor currency pairs\n"
        "• /exotic - Get exotic currency pairs\n"
        "• /random - Get a random forex pair suggestion\n"
        "• /stats - View bot statistics\n"
        "• /help - Get detailed help information\n\n"
        "🔒 <b>Security Features:</b>\n"
        "✓ Rate limiting enabled\n"
        "✓ Access control active\n"
        "✓ All requests logged\n\n"
        "Select a category below to get started!"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("💰 Major Pairs", callback_data='major'),
            InlineKeyboardButton("📊 Minor Pairs", callback_data='minor')
        ],
        [
            InlineKeyboardButton("🌐 Exotic Pairs", callback_data='exotic'),
            InlineKeyboardButton("🎲 Random Pair", callback_data='random')
        ],
        [InlineKeyboardButton("📈 All Pairs", callback_data='all')]
    ]
    
    await update.message.reply_text(
        welcome_message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML
    )
    logger.info(f"User {user.username} (ID: {user.id}) started the bot")

async def pairs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = "📊 <b>Forex Pairs by Category</b>\n\n"
    for category, p_list in FOREX_PAIRS.items():
        message += f"<b>{category} Pairs:</b>\n"
        message += "• " + "\n• ".join(p_list) + "\n\n"
    
    total = sum(len(p) for p in FOREX_PAIRS.values())
    message += f"<i>Total pairs: {total}</i>"
    await update.message.reply_text(message, parse_mode=ParseMode.HTML)

async def get_category_pairs(update: Update, context: ContextTypes.DEFAULT_TYPE, category: str):
    p_list = FOREX_PAIRS.get(category.capitalize(), [])
    if not p_list:
        await update.message.reply_text("Category not found.")
        return
    
    message = f"<b>{category.capitalize()} Currency Pairs:</b>\n\n"
    message += "• " + "\n• ".join(p_list)
    message += f"\n\n<i>Total: {len(p_list)} pairs</i>"
    
    keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]]
    await update.message.reply_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML
    )

async def major(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await get_category_pairs(update, context, 'Major')

async def minor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await get_category_pairs(update, context, 'Minor')

async def exotic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await get_category_pairs(update, context, 'Exotic')

async def random_pair(update: Update, context: ContextTypes.DEFAULT_TYPE):
    all_pairs = [pair for p_list in FOREX_PAIRS.values() for pair in p_list]
    selected_pair = random.choice(all_pairs)
    
    category = next(cat for cat, p_list in FOREX_PAIRS.items() if selected_pair in p_list)
    
    message = (
        f"🎲 <b>Random Pair Selection</b>\n\n"
        f"Pair: <b>{selected_pair}</b>\n"
        f"Category: <i>{category}</i>\n\n"
        f"Good luck with your trading! 📈"
    )
    
    keyboard = [[InlineKeyboardButton("🎲 Get Another", callback_data='random')]]
    await update.message.reply_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats_message = (
        "📊 <b>Bot Statistics</b>\n\n"
        f"Major Pairs: {len(FOREX_PAIRS['Major'])}\n"
        f"Minor Pairs: {len(FOREX_PAIRS['Minor'])}\n"
        f"Exotic Pairs: {len(FOREX_PAIRS['Exotic'])}\n"
        f"Total Pairs: {sum(len(p) for p in FOREX_PAIRS.values())}\n\n"
        f"🕐 Server Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
        f"✅ Bot Status: Online\n"
        f"🔄 Mode: Polling"
    )
    await update.message.reply_text(stats_message, parse_mode=ParseMode.HTML)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🔍 <b>Forex Pairs Bot - Help Guide</b>\n\n"
        "<b>What does this bot do?</b>\n"
        "This bot provides organized access to forex currency pairs.\n\n"
        "<b>Command Reference:</b>\n"
        "• /start - Main menu\n"
        "• /pairs - All pairs list\n"
        "• /major - Major pairs\n"
        "• /minor - Minor pairs\n"
        "• /exotic - Exotic pairs\n"
        "• /random - Random suggestion\n"
        "• /stats - Bot stats\n\n"
        "<b>Pair Categories:</b>\n"
        "📌 <b>Major:</b> Liquid pairs with USD\n"
        "📌 <b>Minor:</b> Cross pairs without USD\n"
        "📌 <b>Exotic:</b> Emerging markets\n"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # Stop the loading animation on the button
    
    data = query.data
    message = ""
    keyboard = []

    # Navigation Logic
    if data == 'back_to_menu':
        message = "Select a category:"
        keyboard = [
            [
                InlineKeyboardButton("💰 Major Pairs", callback_data='major'),
                InlineKeyboardButton("📊 Minor Pairs", callback_data='minor')
            ],
            [
                InlineKeyboardButton("🌐 Exotic Pairs", callback_data='exotic'),
                InlineKeyboardButton("🎲 Random Pair", callback_data='random')
            ],
            [InlineKeyboardButton("📈 All Pairs", callback_data='all')]
        ]
    elif data in ['major', 'minor', 'exotic']:
        cat_name = data.capitalize()
        p_list = FOREX_PAIRS.get(cat_name, [])
        message = f"<b>{cat_name} Currency Pairs:</b>\n\n• " + "\n• ".join(p_list)
        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]]
    elif data == 'all':
        message = "📊 <b>All Forex Pairs</b>\n\n"
        for category, p_list in FOREX_PAIRS.items():
            message += f"<b>{category}:</b>\n• " + "\n• ".join(p_list) + "\n\n"
        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]]
    elif data == 'random':
        all_pairs = [pair for p_list in FOREX_PAIRS.values() for pair in p_list]
        selected_pair = random.choice(all_pairs)
        category = next(cat for cat, p_list in FOREX_PAIRS.items() if selected_pair in p_list)
        message = f"🎲 <b>Random Pair</b>\n\n{selected_pair}\nCategory: <i>{category}</i>"
        keyboard = [
            [InlineKeyboardButton("🎲 Another One", callback_data='random')],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]
        ]
    else:
        message = "Unknown option"
        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]]

    # Edit Message Safely
    try:
        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )
    except BadRequest as e:
        # Ignore "Message is not modified" error if user clicks same button
        if "Message is not modified" not in str(e):
            logger.error(f"Error editing message: {e}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Exception while handling an update:", exc_info=context.error)
    # Only reply if it was a message update
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ An error occurred while processing your request."
            )
        except Exception:
            pass

def main():
    """Main function to run the bot"""
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not found!")
        logger.error("Set it in Render Environment Variables or .env file")
        return

    # Load Authorized Users
    auth_users_str = os.getenv('AUTHORIZED_USERS', '')
    if auth_users_str:
        try:
            ids = [int(uid.strip()) for uid in auth_users_str.split(',') if uid.strip()]
            AUTHORIZED_USERS.update(ids)
            logger.info(f"Loaded {len(AUTHORIZED_USERS)} authorized users")
        except ValueError:
            logger.error("Invalid format in AUTHORIZED_USERS. Use comma-separated IDs.")

    # Start Flask in Background Thread (Daemonized)
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Build Application
    application = Application.builder().token(token).build()

    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("pairs", pairs))
    application.add_handler(CommandHandler("major", major))
    application.add_handler(CommandHandler("minor", minor))
    application.add_handler(CommandHandler("exotic", exotic))
    application.add_handler(CommandHandler("random", random_pair))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    application.add_error_handler(error_handler)

    logger.info("Bot is polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == '__main__':
    main()
