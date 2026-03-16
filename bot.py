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

# Crear un event loop global
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
            <p>Webhook: Configurado</p>
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
        data = request.get_json(force=True)
        if not data:
            logger.warning("⚠️ Datos vacíos")
            return "No data", 400
            
        logger.info(f"📩 Webhook recibido - Update ID: {data.get('update_id')}")
        
        # Crear una tarea en el event loop
        future = asyncio.run_coroutine_threadsafe(
            handle_message(data), 
            loop
        )
        
        # Esperar un poco para asegurar que se procesa (no bloquea)
        future.add_done_callback(lambda f: logger.info("✅ Mensaje procesado correctamente") if not f.exception() else logger.error(f"❌ Error: {f.exception()}"))
        
        return "OK", 200
        
    except Exception as e:
        logger.error(f"❌ Error en webhook: {e}", exc_info=True)
        return "Error", 500

async def handle_message(data):
    """Procesa los mensajes"""
    try:
        logger.info("🔍 Procesando mensaje...")
        
        # Convertir el update de Telegram
        update = telegram.Update.de_json(data, bot)
        
        if update.message and update.message.text:
            chat_id = update.message.chat.id
            text = update.message.text
            user = update.message.from_user.first_name
            
            logger.info(f"💬 Mensaje de {user} (chat {chat_id}): '{text}'")
            
            # Responder según el comando
            if text == '/start':
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"🎉 ¡Hola {user}! Bot funcionando correctamente.\n\nComandos:\n/start - Iniciar\n/help - Ayuda\n/info - Información"
                )
                logger.info(f"✅ Respondido /start a {user}")
                
            elif text == '/help':
                await bot.send_message(
                    chat_id=chat_id,
                    text="📚 Ayuda:\n• /start - Iniciar\n• /help - Esta ayuda\n• /info - Información\n• Cualquier mensaje - Eco"
                )
                logger.info(f"✅ Respondido /help a {user}")
                
            elif text == '/info':
                await bot.send_message(
                    chat_id=chat_id,
                    text="ℹ️ Información:\n• Estado: Activo\n• Modo: Webhook\n• Plataforma: Render\n• Versión: 2.0"
                )
                logger.info(f"✅ Respondido /info a {user}")
                
            else:
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"✉️ Eco: {text}"
                )
                logger.info(f"✅ Respondido eco a {user}")
        else:
            logger.warning("⚠️ Mensaje sin texto o sin message")
            
    except Exception as e:
        logger.error(f"❌ Error procesando mensaje: {e}", exc_info=True)
        # Intentar notificar al usuario del error
        try:
            if update and update.message:
                await bot.send_message(
                    chat_id=update.message.chat.id,
                    text="❌ Ocurrió un error procesando tu mensaje. Los administradores han sido notificados."
                )
        except:
            pass

# Iniciar el loop en segundo plano para procesar tareas
def start_background_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

# Hilo para el event loop
import threading
thread = threading.Thread(target=start_background_loop, args=(loop,), daemon=True)
thread.start()

if __name__ == '__main__':
    # Configurar webhook al iniciar
    if WEBHOOK_URL:
        webhook_url = f"{WEBHOOK_URL}/{TOKEN}"
        logger.info(f"🔧 Configurando webhook en {webhook_url}")
        
        async def setup_webhook():
            result = await bot.set_webhook(url=webhook_url)
            if result:
                logger.info("✅ Webhook configurado exitosamente")
            else:
                logger.error("❌ Error configurando webhook")
            return result
        
        # Ejecutar en el loop
        future = asyncio.run_coroutine_threadsafe(setup_webhook(), loop)
        future.result(timeout=10)  # Esperar hasta 10 segundos
    
    logger.info(f"🚀 Bot iniciado en puerto {PORT}")
    app.run(host='0.0.0.0', port=PORT)