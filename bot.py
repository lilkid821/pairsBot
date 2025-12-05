import os
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from telegram.constants import ParseMode
from functools import wraps
from flask import Flask, jsonify
import threading

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Flask app for Render health checks
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

# Forex pairs data with real-time categories
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

# User access control (in production, use database)
AUTHORIZED_USERS = set()

def authorized_only(func):
    """Decorator to restrict access to authorized users"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        username = update.effective_user.username or "Unknown"
        
        # Log all access attempts
        logger.info(f"Access attempt by user {username} (ID: {user_id})")
        
        # Check if user is authorized (empty set means all users allowed)
        if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
            await update.message.reply_text(
                "⛔ *Access Denied*\n\n"
                "You are not authorized to use this bot.\n"
                "Please contact the administrator.",
                parse_mode=ParseMode.MARKDOWN
            )
            logger.warning(f"Unauthorized access attempt by {username} (ID: {user_id})")
            return
        
        return await func(update, context)
    return wrapper

def rate_limit(max_calls: int = 5, period: int = 60):
    """Rate limiting decorator"""
    calls = {}
    
    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user_id = update.effective_user.id
            current_time = datetime.now().timestamp()
            
            if user_id not in calls:
                calls[user_id] = []
            
            # Remove old calls outside the time window
            calls[user_id] = [
                call_time for call_time in calls[user_id]
                if current_time - call_time < period
            ]
            
            if len(calls[user_id]) >= max_calls:
                await update.message.reply_text(
                    f"⏳ Rate limit exceeded. Please wait before trying again."
                )
                return
            
            calls[user_id].append(current_time)
            return await func(update, context)
        return wrapper
    return decorator

@authorized_only
@rate_limit(max_calls=10, period=60)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    user = update.effective_user
    
    welcome_message = (
        f"👋 *Welcome to Forex Pairs Bot, {user.first_name}!*\n\n"
        "🌍 *Available Commands:*\n"
        "• /start - Show this welcome message\n"
        "• /pairs - View all forex pairs by category\n"
        "• /major - Get major currency pairs\n"
        "• /minor - Get minor currency pairs\n"
        "• /exotic - Get exotic currency pairs\n"
        "• /random - Get a random forex pair suggestion\n"
        "• /stats - View bot statistics\n"
        "• /help - Get detailed help information\n\n"
        "🔒 *Security Features:*\n"
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
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        welcome_message,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )
    
    logger.info(f"User {user.username} (ID: {user.id}) started the bot")

async def pairs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all pairs organized by category"""
    message = "📊 *Forex Pairs by Category*\n\n"
    
    for category, pairs in FOREX_PAIRS.items():
        message += f"*{category} Pairs:*\n"
        message += "• " + "\n• ".join(pairs) + "\n\n"
    
    message += f"_Total pairs: {sum(len(pairs) for pairs in FOREX_PAIRS.values())}_"
    
    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

async def get_category_pairs(update: Update, context: ContextTypes.DEFAULT_TYPE, category: str):
    """Get pairs for a specific category"""
    pairs = FOREX_PAIRS.get(category.capitalize(), [])
    
    if not pairs:
        await update.message.reply_text("Category not found.")
        return
    
    message = f"*{category.capitalize()} Currency Pairs:*\n\n"
    message += "• " + "\n• ".join(pairs)
    message += f"\n\n_Total: {len(pairs)} pairs_"
    
    keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        message,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

async def major(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get major pairs"""
    await get_category_pairs(update, context, 'Major')

async def minor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get minor pairs"""
    await get_category_pairs(update, context, 'Minor')

async def exotic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get exotic pairs"""
    await get_category_pairs(update, context, 'Exotic')

async def random_pair(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get a random forex pair"""
    import random
    
    all_pairs = [pair for pairs in FOREX_PAIRS.values() for pair in pairs]
    selected_pair = random.choice(all_pairs)
    
    # Find category
    category = next(
        cat for cat, pairs in FOREX_PAIRS.items() 
        if selected_pair in pairs
    )
    
    message = (
        f"🎲 *Random Pair Selection*\n\n"
        f"Pair: *{selected_pair}*\n"
        f"Category: _{category}_\n\n"
        f"Good luck with your trading! 📈"
    )
    
    keyboard = [[InlineKeyboardButton("🎲 Get Another", callback_data='random')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        message,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show bot statistics"""
    stats_message = (
        "📊 *Bot Statistics*\n\n"
        f"Major Pairs: {len(FOREX_PAIRS['Major'])}\n"
        f"Minor Pairs: {len(FOREX_PAIRS['Minor'])}\n"
        f"Exotic Pairs: {len(FOREX_PAIRS['Exotic'])}\n"
        f"Total Pairs: {sum(len(pairs) for pairs in FOREX_PAIRS.values())}\n\n"
        f"🕐 Server Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
        f"✅ Bot Status: Online (Polling Mode)\n"
        f"🔄 Mode: Long Polling"
    )
    
    await update.message.reply_text(stats_message, parse_mode=ParseMode.MARKDOWN)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show detailed help"""
    help_text = (
        "🔍 *Forex Pairs Bot - Help Guide*\n\n"
        "*What does this bot do?*\n"
        "This bot provides organized access to forex currency pairs "
        "categorized into Major, Minor, and Exotic pairs.\n\n"
        "*Command Reference:*\n"
        "• `/start` - Initialize bot and show main menu\n"
        "• `/pairs` - Display all pairs organized by category\n"
        "• `/major` - Show major currency pairs (most liquid)\n"
        "• `/minor` - Show minor currency pairs (cross pairs)\n"
        "• `/exotic` - Show exotic currency pairs (emerging markets)\n"
        "• `/random` - Get a random pair suggestion\n"
        "• `/stats` - View bot statistics\n"
        "• `/help` - Show this help message\n\n"
        "*Pair Categories Explained:*\n"
        "📌 *Major Pairs* - Most traded pairs involving USD\n"
        "📌 *Minor Pairs* - Cross currency pairs without USD\n"
        "📌 *Exotic Pairs* - Pairs with emerging market currencies\n\n"
        "*Security:*\n"
        "• Rate limiting: 10 requests per minute\n"
        "• All access attempts are logged\n"
        "• Optional user authorization available\n\n"
        "Need assistance? Contact the administrator."
    )
    
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks"""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'major':
        message = f"*Major Currency Pairs:*\n\n• " + "\n• ".join(FOREX_PAIRS['Major'])
    elif query.data == 'minor':
        message = f"*Minor Currency Pairs:*\n\n• " + "\n• ".join(FOREX_PAIRS['Minor'])
    elif query.data == 'exotic':
        message = f"*Exotic Currency Pairs:*\n\n• " + "\n• ".join(FOREX_PAIRS['Exotic'])
    elif query.data == 'all':
        message = "📊 *All Forex Pairs*\n\n"
        for category, pairs in FOREX_PAIRS.items():
            message += f"*{category}:*\n• " + "\n• ".join(pairs) + "\n\n"
    elif query.data == 'random':
        import random
        all_pairs = [pair for pairs in FOREX_PAIRS.values() for pair in pairs]
        selected_pair = random.choice(all_pairs)
        category = next(cat for cat, pairs in FOREX_PAIRS.items() if selected_pair in pairs)
        message = f"🎲 *Random Pair*\n\n{selected_pair}\nCategory: _{category}_"
    elif query.data == 'back_to_menu':
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
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "Select a category:",
            reply_markup=reply_markup
        )
        return
    else:
        message = "Unknown option"
    
    keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        message,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error(f"Update {update} caused error {context.error}")
    
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "⚠️ An error occurred while processing your request. "
            "Please try again later."
        )

def run_flask():
    """Run Flask app in a separate thread"""
    port = int(os.getenv('PORT', 10000))
    logger.info(f"Starting Flask server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

def main():
    """Main function to run the bot"""
    # Get bot token from environment variable
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment variables!")
        logger.error("Please set TELEGRAM_BOT_TOKEN in your Render environment variables")
        return
    
    logger.info("Bot token loaded successfully")
    
    # Optional: Load authorized users from environment
    auth_users = os.getenv('AUTHORIZED_USERS', '')
    if auth_users:
        AUTHORIZED_USERS.update(int(user_id) for user_id in auth_users.split(',') if user_id.strip())
        logger.info(f"Loaded {len(AUTHORIZED_USERS)} authorized users")
    
    # Start Flask server in background thread for Render health checks
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("Flask health check server started")
    
    # Create application
    application = Application.builder().token(token).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("pairs", pairs))
    application.add_handler(CommandHandler("major", major))
    application.add_handler(CommandHandler("minor", minor))
    application.add_handler(CommandHandler("exotic", exotic))
    application.add_handler(CommandHandler("random", random_pair))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # Start bot with long polling (works on Render!)
    logger.info("Starting bot in polling mode...")
    logger.info("Bot is now running and waiting for messages!")
    
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        poll_interval=1.0,
        timeout=30
    )

if __name__ == '__main__':
    main()
