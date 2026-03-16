import os
import logging
import sys
from flask import Flask, request
import requests
import json

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

# Estado de la calculadora para cada usuario (memoria temporal)
calculadoras = {}

def enviar_mensaje(chat_id, texto, keyboard=None):
    """Envía un mensaje con teclado opcional"""
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": texto,
        "parse_mode": "HTML"
    }
    if keyboard:
        payload["reply_markup"] = json.dumps(keyboard)
    
    requests.post(url, json=payload)

def enviar_accion_escribiendo(chat_id):
    """Muestra 'escribiendo...' en el chat"""
    url = f"https://api.telegram.org/bot{TOKEN}/sendChatAction"
    requests.post(url, json={"chat_id": chat_id, "action": "typing"})

@app.route('/', methods=['GET'])
def home():
    return "Bot de Telegram con Calculadora!"

@app.route('/health', methods=['GET'])
def health():
    return "OK", 200

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    """Procesa mensajes y callbacks de Telegram"""
    try:
        data = request.get_json()
        
        # Procesar callback de botones (cuando alguien presiona un botón)
        if 'callback_query' in data:
            callback = data['callback_query']
            chat_id = callback['message']['chat']['id']
            message_id = callback['message']['message_id']
            data_callback = callback['data']
            
            logger.info(f"🔘 Botón presionado: {data_callback} en chat {chat_id}")
            
            # Responder al callback para quitar el "cargando"
            requests.post(f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery",
                         json={"callback_query_id": callback['id']})
            
            # Inicializar calculadora si no existe
            if chat_id not in calculadoras:
                calculadoras[chat_id] = ""
            
            # Procesar según el botón
            if data_callback == "calc_clear":
                calculadoras[chat_id] = ""
                nuevo_texto = "🧮 Calculadora reiniciada"
                
            elif data_callback == "calc_result":
                try:
                    # Evaluar la expresión
                    expresion = calculadoras[chat_id]
                    if expresion:
                        resultado = eval(expresion)
                        calculadoras[chat_id] = str(resultado)
                        nuevo_texto = f"🧮 <b>{expresion} = {resultado}</b>"
                    else:
                        nuevo_texto = "🧮 Ingresa números primero"
                except:
                    nuevo_texto = "❌ Error en la expresión"
                    calculadoras[chat_id] = ""
            
            elif data_callback == "calc_del":
                # Borrar último carácter
                calculadoras[chat_id] = calculadoras[chat_id][:-1]
                nuevo_texto = f"🧮 <b>{calculadoras[chat_id] or '0'}</b>"
                
            else:
                # Agregar número u operador
                calculadoras[chat_id] += data_callback
                nuevo_texto = f"🧮 <b>{calculadoras[chat_id]}</b>"
            
            # Actualizar el mensaje con el nuevo texto y los botones
            url = f"https://api.telegram.org/bot{TOKEN}/editMessageText"
            payload = {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": nuevo_texto,
                "parse_mode": "HTML",
                "reply_markup": json.dumps(crear_teclado_calculadora())
            }
            requests.post(url, json=payload)
            
            return "OK", 200
        
        # Procesar mensajes normales
        if 'message' in data:
            chat_id = data['message']['chat']['id']
            text = data['message'].get('text', '')
            user = data['message']['from'].get('first_name', 'Usuario')
            
            logger.info(f"💬 Chat {chat_id}: '{text}' de {user}")
            
            # Mostrar "escribiendo..."
            enviar_accion_escribiendo(chat_id)
            
            # Comandos
            if text == '/start':
                enviar_mensaje(chat_id, 
                    f"🎉 ¡Hola {user}! Bot con calculadora interactiva.\n\n"
                    f"Comandos:\n"
                    f"/start - Iniciar\n"
                    f"/help - Ayuda\n"
                    f"/info - Información\n"
                    f"/calc - Abrir calculadora")
            
            elif text == '/help':
                enviar_mensaje(chat_id,
                    "📚 <b>Ayuda</b>\n\n"
                    "• /calc - Abre calculadora con botones\n"
                    "• Envía cualquier mensaje para eco\n"
                    "• Los botones de la calculadora son interactivos")
            
            elif text == '/info':
                enviar_mensaje(chat_id,
                    "ℹ️ <b>Información</b>\n\n"
                    "• Bot en Render\n"
                    "• Versión: 2.0 con calculadora\n"
                    "• Funciones: eco y calculadora")
            
            elif text == '/calc':
                # Abrir calculadora
                calculadoras[chat_id] = ""
                enviar_mensaje(chat_id,
                    "🧮 <b>Calculadora</b>\n\nPresiona los botones para operar",
                    crear_teclado_calculadora())
            
            else:
                # Eco normal
                enviar_mensaje(chat_id, f"✉️ Eco: {text}")
        
        return "OK", 200
        
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        return "Error", 500

def crear_teclado_calculadora():
    """Crea el teclado inline de la calculadora"""
    return {
        "inline_keyboard": [
            [
                {"text": "7", "callback_data": "7"},
                {"text": "8", "callback_data": "8"},
                {"text": "9", "callback_data": "9"},
                {"text": "÷", "callback_data": "/"},
                {"text": "C", "callback_data": "calc_clear"}
            ],
            [
                {"text": "4", "callback_data": "4"},
                {"text": "5", "callback_data": "5"},
                {"text": "6", "callback_data": "6"},
                {"text": "×", "callback_data": "*"},
                {"text": "⌫", "callback_data": "calc_del"}
            ],
            [
                {"text": "1", "callback_data": "1"},
                {"text": "2", "callback_data": "2"},
                {"text": "3", "callback_data": "3"},
                {"text": "-", "callback_data": "-"},
                {"text": " ", "callback_data": "null"}
            ],
            [
                {"text": "0", "callback_data": "0"},
                {"text": ".", "callback_data": "."},
                {"text": "=", "callback_data": "calc_result"},
                {"text": "+", "callback_data": "+"},
                {"text": " ", "callback_data": "null"}
            ]
        ]
    }

if __name__ == '__main__':
    # Configurar webhook
    if WEBHOOK_URL:
        webhook_url = f"{WEBHOOK_URL}/{TOKEN}"
        r = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/setWebhook",
            data={"url": webhook_url}
        )
        if r.status_code == 200 and r.json().get('ok'):
            logger.info("✅ Webhook configurado")
        else:
            logger.error(f"❌ Error webhook: {r.text}")
    
    logger.info(f"🚀 Bot iniciado en puerto {PORT}")
    app.run(host='0.0.0.0', port=PORT)