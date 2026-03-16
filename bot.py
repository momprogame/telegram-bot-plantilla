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

# Función para ejecutar tareas asíncronas de forma segura
def run_async(coro):
    """Ejecuta una corrutina en el event loop global"""
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    try:
        # Esperar un poco para capturar errores inmediatos
        return future.result(timeout=5)
    except asyncio.TimeoutError:
        # La tarea sigue ejecutándose, eso está bien
        logger.debug("Tarea asíncrona continúa en segundo plano")
        return None
    except Exception as e:
        logger.error(f"Error en tarea asíncrona: {e}")
        return None

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
            
        update_id = data.get('update_id', 'desconocido')
        logger.info(f"📩 Webhook recibido - Update ID: {update_id}")
        
        # PROCESAR DIRECTAMENTE AQUÍ (sin async)
        # Esto evita problemas de event loop
        try:
            # Extraer información básica del mensaje
            if 'message' in data and 'text' in data['message']:
                chat_id = data['message']['chat']['id']
                text = data['message']['text']
                user = data['message']['from'].get('first_name', 'Usuario')
                
                logger.info(f"💬 Mensaje de {user} (chat {chat_id}): '{text}'")
                
                # Responder según el comando (usando requests directamente)
                import requests
                
                if text == '/start':
                    requests.post(
                        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                        json={
                            "chat_id": chat_id,
                            "text": f"🎉 ¡Hola {user}! Bot funcionando correctamente.\n\nComandos:\n/start - Iniciar\n/help - Ayuda\n/info - Información"
                        }
                    )
                    logger.info(f"✅ Respondido /start a {user}")
                    
                elif text == '/help':
                    requests.post(
                        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                        json={
                            "chat_id": chat_id,
                            "text": "📚 Ayuda:\n• /start - Iniciar\n• /help - Esta ayuda\n• /info - Información\n• Cualquier mensaje - Eco"
                        }
                    )
                    logger.info(f"✅ Respondido /help a {user}")
                    
                elif text == '/info':
                    requests.post(
                        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                        json={
                            "chat_id": chat_id,
                            "text": "ℹ️ Información:\n• Estado: Activo\n• Modo: Webhook\n• Plataforma: Render\n• Versión: 3.0"
                        }
                    )
                    logger.info(f"✅ Respondido /info a {user}")
                    
                else:
                    requests.post(
                        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                        json={
                            "chat_id": chat_id,
                            "text": f"✉️ Eco: {text}"
                        }
                    )
                    logger.info(f"✅ Respondido eco a {user}")
            else:
                logger.warning("⚠️ Mensaje sin texto")
                
        except Exception as e:
            logger.error(f"❌ Error procesando mensaje: {e}", exc_info=True)
        
        return "OK", 200
        
    except Exception as e:
        logger.error(f"❌ Error en webhook: {e}", exc_info=True)
        return "Error", 500

@app.errorhandler(Exception)
def handle_error(e):
    logger.error(f"Error no manejado: {e}", exc_info=True)
    return "Error", 500

if __name__ == '__main__':
    # Configurar webhook al iniciar usando requests
    if WEBHOOK_URL:
        webhook_url = f"{WEBHOOK_URL}/{TOKEN}"
        logger.info(f"🔧 Configurando webhook en {webhook_url}")
        
        import requests
        response = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/setWebhook",
            data={"url": webhook_url}
        )
        
        if response.status_code == 200 and response.json().get('ok'):
            logger.info("✅ Webhook configurado exitosamente")
        else:
            logger.error(f"❌ Error configurando webhook: {response.text}")
    
    logger.info(f"🚀 Bot iniciado en puerto {PORT}")
    app.run(host='0.0.0.0', port=PORT)