import os
import logging
import sys
import asyncio
from flask import Flask, request
import telegram

# Configuración
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

# Crear un event loop global para toda la aplicación
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

@app.route('/', methods=['GET'])
def home():
    return """
    <html>
        <head><title>Bot de Telegram</title></head>
        <body>
            <h1>🤖 Bot de Telegram Activo</h1>
            <p>Estado: 🟢 Funcionando</p>
        </body>
    </html>
    """

@app.route('/health', methods=['GET'])
def health():
    return "OK", 200

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    """Endpoint principal para Telegram"""
    try:
        logger.info("📩 Webhook recibido")
        
        # Obtener datos
        data = request.get_json(force=True)
        if not data:
            logger.warning("⚠️ Datos vacíos")
            return "No data", 400
            
        logger.info(f"Update ID: {data.get('update_id')}")
        
        # Ejecutar la función handle_message en el event loop global
        future = asyncio.run_coroutine_threadsafe(
            handle_message(data), 
            loop
        )
        
        # Esperar un momento para asegurar que se programó (no bloqueante)
        future.add_done_callback(lambda f: logger.info("✅ Mensaje procesado") if not f.exception() else logger.error(f"❌ Error: {f.exception()}"))
        
        return "OK", 200
        
    except Exception as e:
        logger.error(f"❌ Error en webhook: {e}", exc_info=True)
        return "Error", 500

async def handle_message(data):
    """Procesa los mensajes de forma asíncrona"""
    try:
        update = telegram.Update.de_json(data, bot)
        
        if update.message and update.message.text:
            chat_id = update.message.chat.id
            text = update.message.text
            
            logger.info(f"Mensaje de {chat_id}: '{text}'")
            
            # Responder según el comando
            if text == '/start':
                await bot.send_message(
                    chat_id=chat_id,
                    text="🎉 ¡Bot funcionando correctamente!\n\nComandos:\n/start - Iniciar\n/help - Ayuda\n/info - Información"
                )
            elif text == '/help':
                await bot.send_message(
                    chat_id=chat_id,
                    text="📚 Ayuda del bot:\n• Este bot responde a comandos\n• También hace eco de mensajes"
                )
            elif text == '/info':
                await bot.send_message(
                    chat_id=chat_id,
                    text="ℹ️ Información:\n• Estado: Activo\n• Modo: Webhook\n• Plataforma: Render"
                )
            else:
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"✉️ Eco: {text}"
                )
                
    except Exception as e:
        logger.error(f"Error procesando mensaje: {e}", exc_info=True)

@app.errorhandler(Exception)
def handle_error(e):
    logger.error(f"Error no manejado: {e}", exc_info=True)
    return "Error", 500

if __name__ == '__main__':
    # Configurar webhook al iniciar
    if WEBHOOK_URL:
        webhook_url = f"{WEBHOOK_URL}/{TOKEN}"
        logger.info(f"Configurando webhook en {webhook_url}")
        
        # Ejecutar en el event loop
        async def setup_webhook():
            await bot.set_webhook(url=webhook_url)
            logger.info("✅ Webhook configurado exitosamente")
        
        loop.run_until_complete(setup_webhook())
    
    logger.info(f"🚀 Bot iniciado en puerto {PORT}")
    app.run(host='0.0.0.0', port=PORT)
