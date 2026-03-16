import os
import logging
import sys
from flask import Flask, request, jsonify
import telegram
import asyncio

# Configuración básica
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
PORT = int(os.environ.get('PORT', 8080))

# Validación
if not TOKEN:
    logging.error("❌ TELEGRAM_BOT_TOKEN no configurado")
    sys.exit(1)

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Inicializar Flask y Bot
app = Flask(__name__)
bot = telegram.Bot(token=TOKEN)

# Almacén simple para evitar múltiples inicializaciones
_initialized = False

async def initialize_bot():
    """Inicializa el bot y configura webhook"""
    global _initialized
    if not _initialized and WEBHOOK_URL:
        webhook_url = f"{WEBHOOK_URL}/{TOKEN}"
        await bot.set_webhook(url=webhook_url)
        logger.info(f"✅ Webhook configurado: {webhook_url}")
        _initialized = True

async def handle_message(update):
    """Procesa los mensajes entrantes"""
    try:
        message = update.get('message')
        if not message:
            return
        
        chat_id = message['chat']['id']
        text = message.get('text', '')
        
        logger.info(f"Mensaje recibido: '{text}' de chat {chat_id}")
        
        if text == '/start':
            await bot.send_message(
                chat_id=chat_id,
                text="🤖 ¡Hola! Bot funcionando correctamente en Render.\nComandos: /start, /help, /info"
            )
        elif text == '/help':
            await bot.send_message(
                chat_id=chat_id,
                text="📚 Ayuda:\n• /start - Iniciar\n• /help - Esta ayuda\n• /info - Información"
            )
        elif text == '/info':
            await bot.send_message(
                chat_id=chat_id,
                text="ℹ️ Bot desplegado en Render 24/7\nModo: Webhook"
            )
        elif text:
            await bot.send_message(
                chat_id=chat_id,
                text=f"✉️ Eco: {text}"
            )
            
    except Exception as e:
        logger.error(f"Error en handle_message: {e}", exc_info=True)

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "status": "ok",
        "message": "Bot de Telegram activo",
        "webhook": "configurado" if WEBHOOK_URL else "no configurado"
    })

@app.route('/health', methods=['GET'])
def health():
    return "OK", 200

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    """Endpoint principal para Telegram"""
    try:
        # Log de la petición recibida
        logger.info("📩 Webhook recibido")
        
        # Obtener y validar datos
        data = request.get_json(force=True)
        if not data:
            logger.warning("⚠️ Datos vacíos en webhook")
            return "No data", 400
            
        logger.info(f"Update ID: {data.get('update_id')}")
        
        # Procesar el mensaje de manera asíncrona
        asyncio.create_task(handle_message(data))
        
        # Responder inmediatamente a Telegram
        return "OK", 200
        
    except Exception as e:
        logger.error(f"❌ Error en webhook: {e}", exc_info=True)
        return "Error", 500

@app.errorhandler(Exception)
def handle_error(e):
    logger.error(f"Error no manejado: {e}", exc_info=True)
    return "Internal Server Error", 500

if __name__ == '__main__':
    # Inicializar webhook al arrancar
    asyncio.run(initialize_bot())
    logger.info(f"🚀 Bot iniciado en puerto {PORT}")
    app.run(host='0.0.0.0', port=PORT, debug=False)
