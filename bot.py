import os
import logging
import sys
from flask import Flask, request
import requests

# Configuración básica
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
PORT = int(os.environ.get('PORT', 10000))

# Validación
if not TOKEN:
    print("ERROR: TELEGRAM_BOT_TOKEN no configurado")
    sys.exit(1)

# Logging simple
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route('/', methods=['GET'])
def home():
    return "Bot de Telegram activo!"

@app.route('/health', methods=['GET'])
def health():
    return "OK", 200

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    """Procesa mensajes de Telegram"""
    try:
        data = request.get_json()
        logger.info(f"📩 Mensaje recibido: {data}")
        
        # Extraer información del mensaje
        if 'message' in data:
            chat_id = data['message']['chat']['id']
            text = data['message'].get('text', '')
            user = data['message']['from'].get('first_name', 'Usuario')
            
            logger.info(f"💬 Chat {chat_id}: '{text}' de {user}")
            
            # Respuesta según comando
            if text == '/start':
                respuesta = f"🎉 ¡Hola {user}! Bot funcionando correctamente."
            elif text == '/help':
                respuesta = "📚 Comandos: /start, /help, /info"
            elif text == '/info':
                respuesta = "ℹ️ Bot en Render - Versión simple"
            else:
                respuesta = f"✉️ Eco: {text}"
            
            # Enviar respuesta usando requests
            requests.post(
                f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": respuesta}
            )
            logger.info(f"✅ Respuesta enviada a {user}")
        
        return "OK", 200
        
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        return "Error", 500

if __name__ == '__main__':
    # Configurar webhook
    if WEBHOOK_URL:
        webhook_url = f"{WEBHOOK_URL}/{TOKEN}"
        r = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/setWebhook",
            data={"url": webhook_url}
        )
        if r.status_code == 200:
            logger.info("✅ Webhook configurado")
        else:
            logger.error(f"❌ Error webhook: {r.text}")
    
    logger.info(f"🚀 Bot iniciado en puerto {PORT}")
    app.run(host='0.0.0.0', port=PORT)