#!/usr/bin/env python3
"""
Bot de Telegram Plantilla
"""

import os
import logging
import sys
from flask import Flask, request
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import asyncio

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuración del bot
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL', '')
PORT = int(os.environ.get('PORT', 8080))

if not TOKEN:
    logger.error("No se encontró TELEGRAM_BOT_TOKEN")
    sys.exit(1)

app = Flask(__name__)
bot = Bot(token=TOKEN)
application = None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"¡Hola {user.first_name}! 👋\n"
        f"Soy un bot plantilla funcionando correctamente.\n"
        f"Comandos: /start, /help, /info"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Ayuda del Bot\n\n"
        "Este es un bot plantilla que puedes personalizar."
    )

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📊 Información:\n"
        f"• Estado: 🟢 Activo\n"
        f"• Modo: {'Webhook' if WEBHOOK_URL else 'Polling'}\n"
        f"• Versión: 1.0"
    )

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Recibí: {update.message.text}")

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    if request.method == 'POST':
        update = Update.de_json(request.get_json(force=True), bot)
        asyncio.run_coroutine_threadsafe(
            application.process_update(update), 
            application.loop
        )
        return 'OK', 200
    return 'Method not allowed', 405

@app.route('/')
def index():
    return "<h1>🤖 Bot de Telegram Activo</h1><p>El bot está funcionando correctamente.</p>"

def setup_application():
    global application
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("info", info))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    return application

def run_polling():
    logger.info("Iniciando bot en modo polling...")
    app_polling = setup_application()
    app_polling.run_polling(allowed_updates=Update.ALL_TYPES)

def run_webhook():
    global application
    logger.info(f"Iniciando bot en modo webhook en puerto {PORT}...")
    application = setup_application()
    asyncio.run(application.initialize())
    asyncio.run(application.start())
    webhook_url = f"{WEBHOOK_URL}/{TOKEN}"
    asyncio.run(bot.set_webhook(url=webhook_url))
    logger.info(f"Webhook configurado: {webhook_url}")
    app.run(host='0.0.0.0', port=PORT)

def main():
    if WEBHOOK_URL:
        run_webhook()
    else:
        run_polling()

if __name__ == '__main__':
    main()
