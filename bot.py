#!/usr/bin/env python3
"""
Bot de Telegram Plantilla - Versión Corregida para Render
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

# Configuración
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL', '')
PORT = int(os.environ.get('PORT', 8080))

if not TOKEN:
    logger.error("No se encontró TELEGRAM_BOT_TOKEN")
    sys.exit(1)

# Inicializar Flask y Bot
app = Flask(__name__)
bot = Bot(token=TOKEN)

# Inicializar Application (se configurará después)
application = None

# --- COMANDOS DEL BOT ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"¡Hola {user.first_name}! 👋\n"
        f"Bot funcionando correctamente en Render.\n"
        f"Comandos: /start, /help, /info"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Ayuda del Bot\n\n"
        "Este bot está desplegado en Render 24/7.\n"
        "Usa /info para ver el estado."
    )

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📊 Información:\n"
        f"• Estado: 🟢 Activo en Render\n"
        f"• Modo: Webhook\n"
        f"• Versión: 1.0"
    )

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Recibí: {update.message.text}")

# --- CONFIGURACIÓN DE LA APLICACIÓN ---
def setup_application():
    global application
    application = Application.builder().token(TOKEN).build()
    
    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("info", info))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    
    return application

# --- RUTAS DE FLASK ---
@app.route('/')
def index():
    return """
    <html>
        <head><title>Bot de Telegram</title></head>
        <body>
            <h1>🤖 Bot de Telegram Activo en Render</h1>
            <p>El bot está funcionando correctamente.</p>
            <p>Webhook configurado: {}<p>
        </body>
    </html>
    """.format("Sí" if WEBHOOK_URL else "No")

@app.route('/health')
def health():
    return 'OK', 200

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    """Endpoint principal para Telegram"""
    if request.method == 'POST':
        try:
            update = Update.de_json(request.get_json(force=True), bot)
            # Procesar update de manera asíncrona
            asyncio.run_coroutine_threadsafe(
                application.process_update(update), 
                application.loop
            )
            return 'OK', 200
        except Exception as e:
            logger.error(f"Error procesando update: {e}")
            return 'Error', 500
    return 'Method not allowed', 405

# --- FUNCIÓN PRINCIPAL ---
def main():
    """Punto de entrada"""
    global application
    
    # Configurar aplicación
    application = setup_application()
    
    # Inicializar aplicación (crea el loop)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(application.initialize())
    loop.run_until_complete(application.start())
    
    # Configurar webhook si tenemos WEBHOOK_URL
    if WEBHOOK_URL:
        webhook_url = f"{WEBHOOK_URL}/{TOKEN}"
        loop.run_until_complete(bot.set_webhook(url=webhook_url))
        logger.info(f"✅ Webhook configurado en: {webhook_url}")
    else:
        logger.warning("⚠️ WEBHOOK_URL no configurada, el bot no recibirá mensajes")
    
    # Ejecutar Flask
    app.run(host='0.0.0.0', port=PORT)

if __name__ == '__main__':
    main()
