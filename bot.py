import os
import logging
import sys
from flask import Flask, request
import requests
import json
import psutil
import platform
import datetime

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

# ============================================
# FUNCIONES DE UTILIDAD
# ============================================

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

# ============================================
# FUNCIONES DE LA CALCULADORA
# ============================================

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

# ============================================
# FUNCIONES DE INFORMACIÓN DEL SISTEMA
# ============================================

def obtener_info_sistema():
    """Obtiene información detallada del sistema (Render)"""
    info = {}
    
    # Uptime
    boot_time = datetime.datetime.fromtimestamp(psutil.boot_time())
    uptime = datetime.datetime.now() - boot_time
    days = uptime.days
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    info['uptime'] = f"{days}d {hours}h {minutes}m"
    
    # CPU
    info['cpu_percent'] = psutil.cpu_percent(interval=1)
    info['cpu_count'] = psutil.cpu_count()
    cpu_freq = psutil.cpu_freq()
    info['cpu_freq'] = round(cpu_freq.current, 2) if cpu_freq else 0
    
    # RAM
    mem = psutil.virtual_memory()
    info['ram_total'] = round(mem.total / (1024**3), 2)  # GB
    info['ram_used'] = round(mem.used / (1024**3), 2)
    info['ram_percent'] = mem.percent
    
    # Disco
    disk = psutil.disk_usage('/')
    info['disk_total'] = round(disk.total / (1024**3), 2)
    info['disk_used'] = round(disk.used / (1024**3), 2)
    info['disk_percent'] = disk.percent
    
    # Sistema operativo
    info['os'] = platform.system()
    info['os_release'] = platform.release()
    info['hostname'] = platform.node()
    
    # IP pública (para saber dónde está desplegado)
    try:
        info['public_ip'] = requests.get('https://api.ipify.org', timeout=3).text
    except:
        info['public_ip'] = 'No disponible'
    
    return info

def formatear_info_sistema(info):
    """Formatea la información en un mensaje bonito"""
    return f"""🖥️ <b>INFORMACIÓN DEL SISTEMA (RENDER)</b>

⏱️ <b>Uptime:</b> {info['uptime']}
💻 <b>Hostname:</b> {info['hostname']}
🖧 <b>Sistema:</b> {info['os']} {info['os_release']}
🌐 <b>IP Pública:</b> {info['public_ip']}

⚡ <b>CPU:</b> {info['cpu_percent']}% de uso
   • Núcleos: {info['cpu_count']}
   • Frecuencia: {info['cpu_freq']} MHz

🧠 <b>RAM:</b> {info['ram_used']} GB / {info['ram_total']} GB
   • {info['ram_percent']}% usado
   • {'🟢' if info['ram_percent'] < 70 else '🟡' if info['ram_percent'] < 90 else '🔴'} Estado: {'Bien' if info['ram_percent'] < 70 else 'Atención' if info['ram_percent'] < 90 else 'Crítico'}

💾 <b>Disco:</b> {info['disk_used']} GB / {info['disk_total']} GB
   • {info['disk_percent']}% usado
   • {'🟢' if info['disk_percent'] < 70 else '🟡' if info['disk_percent'] < 90 else '🔴'} Estado: {'Bien' if info['disk_percent'] < 70 else 'Atención' if info['disk_percent'] < 90 else 'Crítico'}
"""

# ============================================
# RUTAS DE FLASK (WEBHOOK)
# ============================================

@app.route('/', methods=['GET'])
def home():
    return "Bot de Telegram: Calculadora + Sysinfo"

@app.route('/health', methods=['GET'])
def health():
    return "OK", 200

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    """Procesa mensajes y callbacks de Telegram"""
    try:
        data = request.get_json()
        
        # ========================================
        # PROCESAR CALLBACKS DE BOTONES (CALCULADORA)
        # ========================================
        if 'callback_query' in data:
            callback = data['callback_query']
            chat_id = callback['message']['chat']['id']
            message_id = callback['message']['message_id']
            data_callback = callback['data']
            
            logger.info(f"🔘 Botón presionado: {data_callback}")
            
            # Responder al callback para quitar el "cargando"
            requests.post(f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery",
                         json={"callback_query_id": callback['id']})
            
            # Si es un callback nulo, no hacer nada
            if data_callback == "null":
                return "OK", 200
            
            # Inicializar calculadora si no existe
            if chat_id not in calculadoras:
                calculadoras[chat_id] = ""
            
            # Procesar según el botón
            if data_callback == "calc_clear":
                calculadoras[chat_id] = ""
                nuevo_texto = "🧮 Calculadora reiniciada"
                
            elif data_callback == "calc_result":
                try:
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
                calculadoras[chat_id] = calculadoras[chat_id][:-1]
                nuevo_texto = f"🧮 <b>{calculadoras[chat_id] or '0'}</b>"
                
            else:
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
        
        # ========================================
        # PROCESAR MENSAJES NORMALES
        # ========================================
        if 'message' in data:
            chat_id = data['message']['chat']['id']
            text = data['message'].get('text', '')
            user = data['message']['from'].get('first_name', 'Usuario')
            
            logger.info(f"💬 Mensaje: '{text}' de {user}")
            
            # Mostrar "escribiendo..."
            enviar_accion_escribiendo(chat_id)
            
            # ========== COMANDOS ==========
            if text == '/start':
                enviar_mensaje(chat_id, 
                    f"🎉 ¡Hola {user}! Bot con dos funciones:\n\n"
                    f"🧮 <b>/calc</b> - Calculadora interactiva\n"
                    f"🖥️ <b>/sysinfo</b> - Info del sistema (Render)")
            
            elif text == '/help':
                enviar_mensaje(chat_id,
                    "<b>📚 COMANDOS DISPONIBLES</b>\n\n"
                    "🧮 <b>/calc</b> - Abre calculadora con botones\n"
                    "   • Operaciones: + - × ÷ . =\n"
                    "   • C = Limpiar todo\n"
                    "   • ⌫ = Borrar último\n\n"
                    "🖥️ <b>/sysinfo</b> - Muestra:\n"
                    "   • Uptime del servidor\n"
                    "   • Uso de CPU, RAM y Disco\n"
                    "   • IP pública\n\n"
                    "❓ <b>/help</b> - Esta ayuda")
            
            elif text == '/calc':
                calculadoras[chat_id] = ""
                enviar_mensaje(chat_id,
                    "🧮 <b>Calculadora</b>\n\nPresiona los botones para operar",
                    crear_teclado_calculadora())
            
            elif text == '/sysinfo':
                enviar_accion_escribiendo(chat_id)
                info = obtener_info_sistema()
                mensaje = formatear_info_sistema(info)
                enviar_mensaje(chat_id, mensaje)
            
            else:
                # Mensaje no reconocido
                enviar_mensaje(chat_id, 
                    f"✉️ Comando no reconocido. Usa /help para ver las opciones disponibles.")
        
        return "OK", 200
        
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        return "Error", 500

# ============================================
# INICIO DE LA APLICACIÓN
# ============================================

if __name__ == '__main__':
    # Configurar webhook
    if WEBHOOK_URL:
        webhook_url = f"{WEBHOOK_URL}/{TOKEN}"
        logger.info(f"🔧 Configurando webhook...")
        
        r = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/setWebhook",
            data={"url": webhook_url}
        )
        
        if r.status_code == 200 and r.json().get('ok'):
            logger.info("✅ Webhook configurado correctamente")
        else:
            logger.error(f"❌ Error: {r.text}")
    
    logger.info(f"🚀 Bot iniciado en puerto {PORT}")
    app.run(host='0.0.0.0', port=PORT)