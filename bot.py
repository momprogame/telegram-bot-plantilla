import os
import logging
import sys
from flask import Flask, request
import requests
import json
import psutil
import platform
import datetime

# ============================================
# CONFIGURACIÓN
# ============================================
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
PORT = int(os.environ.get('PORT', 10000))

# API Key de UptimeRobot
UPTIMEROBOT_API_KEY = "u3358345-5c4ed5db967b687a061c90e0"
UPTIMEROBOT_API_URL = "https://api.uptimerobot.com/v2"

# Validación
if not TOKEN:
    print("ERROR: TELEGRAM_BOT_TOKEN no configurado")
    sys.exit(1)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Estados de conversación para cada usuario
user_states = {}

# ============================================
# FUNCIONES DE UTILIDAD
# ============================================

def enviar_mensaje(chat_id, texto, keyboard=None, parse_mode="HTML"):
    """Envía un mensaje con teclado opcional"""
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": texto,
        "parse_mode": parse_mode
    }
    if keyboard:
        payload["reply_markup"] = json.dumps(keyboard)
    
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        logger.error(f"Error enviando mensaje: {e}")

def enviar_accion_escribiendo(chat_id):
    """Muestra 'escribiendo...' en el chat"""
    url = f"https://api.telegram.org/bot{TOKEN}/sendChatAction"
    try:
        requests.post(url, json={"chat_id": chat_id, "action": "typing"}, timeout=3)
    except:
        pass

def editar_mensaje(chat_id, message_id, texto, keyboard=None):
    """Edita un mensaje existente"""
    url = f"https://api.telegram.org/bot{TOKEN}/editMessageText"
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": texto,
        "parse_mode": "HTML"
    }
    if keyboard:
        payload["reply_markup"] = json.dumps(keyboard)
    
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        logger.error(f"Error editando mensaje: {e}")

def responder_callback(callback_id, texto="", mostrar_alerta=False):
    """Responde a un callback query"""
    url = f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery"
    payload = {
        "callback_query_id": callback_id,
        "text": texto,
        "show_alert": mostrar_alerta
    }
    try:
        requests.post(url, json=payload, timeout=3)
    except:
        pass

# ============================================
# FUNCIONES DE UPTIMEROBOT
# ============================================

def uptimerobot_request(action, params=None):
    """Hace una petición a la API de UptimeRobot"""
    if params is None:
        params = {}
    
    headers = {
        "content-type": "application/x-www-form-urlencoded",
        "cache-control": "no-cache"
    }
    
    data = {
        "api_key": UPTIMEROBOT_API_KEY,
        "format": "json"
    }
    data.update(params)
    
    try:
        response = requests.post(f"{UPTIMEROBOT_API_URL}/{action}", data=data, headers=headers, timeout=10)
        return response.json()
    except Exception as e:
        logger.error(f"Error en UptimeRobot API: {e}")
        return {"stat": "fail", "error": str(e)}

def obtener_monitores():
    """Obtiene lista de monitores"""
    result = uptimerobot_request("getMonitors", {
        "logs": 0,
        "response_times": 1,
        "custom_uptime_ratios": 1
    })
    
    if result.get("stat") == "ok":
        return result.get("monitors", [])
    return []

def crear_monitor(url, nombre=None, tipo=1, intervalo=300):
    """Crea un nuevo monitor
    tipo: 1=HTTP(s), 2=Keyword, 3=Ping, 4=Port
    """
    if not nombre:
        nombre = url
    
    params = {
        "friendly_name": nombre,
        "url": url,
        "type": tipo,
        "interval": intervalo
    }
    
    result = uptimerobot_request("newMonitor", params)
    return result

def eliminar_monitor(monitor_id):
    """Elimina un monitor por ID"""
    result = uptimerobot_request("deleteMonitor", {"id": monitor_id})
    return result

def pausar_monitor(monitor_id):
    """Pausa un monitor"""
    result = uptimerobot_request("editMonitor", {
        "id": monitor_id,
        "status": 0
    })
    return result

def reanudar_monitor(monitor_id):
    """Reanuda un monitor"""
    result = uptimerobot_request("editMonitor", {
        "id": monitor_id,
        "status": 1
    })
    return result

def obtener_estado_texto(status):
    """Convierte código de estado a texto"""
    estados = {
        0: "⏸️ Pausado",
        1: "🔄 No verificado aún",
        2: "✅ Activo (OK)",
        8: "📶 Parece caído",
        9: "🔴 Caído"
    }
    return estados.get(status, "❓ Desconocido")

def obtener_color_estado(status):
    """Devuelve emoji según estado"""
    colores = {
        0: "⚪",
        1: "🟡",
        2: "🟢",
        8: "🟠",
        9: "🔴"
    }
    return colores.get(status, "⚫")

def verificar_web_directa(url):
    """Verifica directamente si una web está online"""
    try:
        start = datetime.datetime.now()
        r = requests.get(url, timeout=10, allow_redirects=True)
        end = datetime.datetime.now()
        response_time = (end - start).total_seconds() * 1000  # ms
        
        if r.status_code < 400:
            return {
                "online": True,
                "status_code": r.status_code,
                "response_time": round(response_time, 2),
                "error": None
            }
        else:
            return {
                "online": False,
                "status_code": r.status_code,
                "response_time": round(response_time, 2),
                "error": f"HTTP {r.status_code}"
            }
    except requests.exceptions.Timeout:
        return {"online": False, "error": "Timeout (10s)", "status_code": None}
    except requests.exceptions.ConnectionError:
        return {"online": False, "error": "Error de conexión", "status_code": None}
    except Exception as e:
        return {"online": False, "error": str(e)[:50], "status_code": None}

# ============================================
# TECLADOS (BOTONES)
# ============================================

def teclado_principal():
    """Teclado principal del bot"""
    return {
        "inline_keyboard": [
            [
                {"text": "➕ AGREGAR WEB", "callback_data": "menu_add"},
                {"text": "📋 ESTADO", "callback_data": "menu_status"}
            ],
            [
                {"text": "✏️ EDITAR", "callback_data": "menu_edit"},
                {"text": "❌ ELIMINAR", "callback_data": "menu_delete"}
            ],
            [
                {"text": "🔄 VERIFICAR WEB", "callback_data": "menu_isup"},
                {"text": "📊 MÉTRICAS", "callback_data": "menu_metrics"}
            ],
            [
                {"text": "🖥️ SISTEMA", "callback_data": "menu_sysinfo"},
                {"text": "❓ AYUDA", "callback_data": "menu_help"}
            ]
        ]
    }

def teclado_cancelar():
    """Teclado para cancelar operación"""
    return {
        "inline_keyboard": [
            [{"text": "❌ CANCELAR", "callback_data": "cancelar"}]
        ]
    }

def teclado_monitores(monitores, accion="seleccionar"):
    """Crea teclado con lista de monitores"""
    keyboard = []
    for m in monitores[:10]:  # Máximo 10 para no saturar
        color = obtener_color_estado(m['status'])
        nombre = m['friendly_name'][:20]
        callback = f"monitor_{m['id']}_{accion}"
        keyboard.append([
            {"text": f"{color} {nombre}", "callback_data": callback}
        ])
    
    keyboard.append([{"text": "🏠 VOLVER", "callback_data": "menu_inicio"}])
    return {"inline_keyboard": keyboard}

def teclado_acciones_monitor(monitor_id, monitor_nombre):
    """Teclado de acciones para un monitor específico"""
    return {
        "inline_keyboard": [
            [
                {"text": "⏸️ PAUSAR", "callback_data": f"pause_{monitor_id}"},
                {"text": "▶️ REANUDAR", "callback_data": f"resume_{monitor_id}"}
            ],
            [
                {"text": "📊 MÉTRICAS", "callback_data": f"metrics_{monitor_id}"},
                {"text": "❌ ELIMINAR", "callback_data": f"delete_{monitor_id}"}
            ],
            [{"text": "🔙 VOLVER", "callback_data": "menu_status"}]
        ]
    }

# ============================================
# FUNCIONES DE INFORMACIÓN DEL SISTEMA
# ============================================

def obtener_info_sistema():
    """Obtiene información del sistema (Render)"""
    info = {}
    
    boot_time = datetime.datetime.fromtimestamp(psutil.boot_time())
    uptime = datetime.datetime.now() - boot_time
    days = uptime.days
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    info['uptime'] = f"{days}d {hours}h {minutes}m"
    
    info['cpu_percent'] = psutil.cpu_percent(interval=1)
    info['cpu_count'] = psutil.cpu_count()
    
    mem = psutil.virtual_memory()
    info['ram_total'] = round(mem.total / (1024**3), 2)
    info['ram_used'] = round(mem.used / (1024**3), 2)
    info['ram_percent'] = mem.percent
    
    disk = psutil.disk_usage('/')
    info['disk_total'] = round(disk.total / (1024**3), 2)
    info['disk_used'] = round(disk.used / (1024**3), 2)
    info['disk_percent'] = disk.percent
    
    info['os'] = platform.system()
    info['hostname'] = platform.node()
    
    try:
        info['public_ip'] = requests.get('https://api.ipify.org', timeout=3).text
    except:
        info['public_ip'] = 'No disponible'
    
    return info

def formatear_info_sistema(info):
    """Formatea la información del sistema"""
    ram_color = '🟢' if info['ram_percent'] < 70 else '🟡' if info['ram_percent'] < 90 else '🔴'
    disk_color = '🟢' if info['disk_percent'] < 70 else '🟡' if info['disk_percent'] < 90 else '🔴'
    
    return f"""🖥️ <b>SISTEMA (RENDER)</b>

⏱️ <b>Uptime:</b> {info['uptime']}
💻 <b>Hostname:</b> {info['hostname']}
🌐 <b>IP:</b> {info['public_ip']}

⚡ <b>CPU:</b> {info['cpu_percent']}% ({info['cpu_count']} núcleos)

🧠 <b>RAM:</b> {info['ram_used']}GB / {info['ram_total']}GB ({info['ram_percent']}%) {ram_color}

💾 <b>Disco:</b> {info['disk_used']}GB / {info['disk_total']}GB ({info['disk_percent']}%) {disk_color}
"""

# ============================================
# PROCESAR COMANDOS Y CALLBACKS
# ============================================

@app.route('/', methods=['GET'])
def home():
    return "Bot UptimeRobot en Español - Activo"

@app.route('/health', methods=['GET'])
def health():
    return "OK", 200

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        
        # ========== CALLBACKS DE BOTONES ==========
        if 'callback_query' in data:
            callback = data['callback_query']
            chat_id = callback['message']['chat']['id']
            message_id = callback['message']['message_id']
            data_callback = callback['data']
            callback_id = callback['id']
            
            logger.info(f"🔘 Callback: {data_callback}")
            
            # ===== CANCELAR =====
            if data_callback == "cancelar":
                user_states.pop(chat_id, None)
                editar_mensaje(chat_id, message_id, "✅ Operación cancelada", teclado_principal())
                responder_callback(callback_id)
                return "OK", 200
            
            # ===== MENÚ PRINCIPAL =====
            if data_callback == "menu_inicio":
                editar_mensaje(chat_id, message_id, 
                    "🏠 <b>MENÚ PRINCIPAL</b>\n\nSelecciona una opción:", teclado_principal())
                responder_callback(callback_id)
                return "OK", 200
            
            if data_callback == "menu_help":
                ayuda = """<b>❓ AYUDA - UptimeRobot Bot</b>

<b>📋 COMANDOS DISPONIBLES:</b>

➕ <b>AGREGAR WEB</b> - Añade un sitio a monitorear
📋 <b>ESTADO</b> - Ver estado de tus webs
✏️ <b>EDITAR</b> - Modificar configuración
❌ <b>ELIMINAR</b> - Eliminar un monitor
🔄 <b>VERIFICAR WEB</b> - Comprobar si una web está online
📊 <b>MÉTRICAS</b> - Ver tiempos de respuesta
🖥️ <b>SISTEMA</b> - Info del servidor

<b>🔹 CÓMO USAR:</b>
• Usa los botones para navegar
• Para agregar una web, escribe la URL cuando te lo pida
• Puedes cancelar cualquier operación con CANCELAR

<b>📊 ESTADOS:</b>
🟢 Activo (OK)   🔴 Caído
🟠 Parece caído   ⚪ Pausado
🟡 No verificado

<i>Desarrollado con UptimeRobot API</i>"""
                
                editar_mensaje(chat_id, message_id, ayuda, teclado_principal())
                responder_callback(callback_id)
                return "OK", 200
            
            if data_callback == "menu_sysinfo":
                enviar_accion_escribiendo(chat_id)
                info = obtener_info_sistema()
                mensaje = formatear_info_sistema(info)
                editar_mensaje(chat_id, message_id, mensaje, teclado_principal())
                responder_callback(callback_id)
                return "OK", 200
            
            if data_callback == "menu_status":
                enviar_accion_escribiendo(chat_id)
                monitores = obtener_monitores()
                
                if not monitores:
                    texto = "📋 <b>No tienes webs monitoreadas</b>\n\nUsa 'AGREGAR WEB' para empezar."
                    editar_mensaje(chat_id, message_id, texto, teclado_principal())
                else:
                    texto = "📋 <b>TUS WEBS MONITOREADAS</b>\n\nSelecciona una para ver detalles:"
                    editar_mensaje(chat_id, message_id, texto, teclado_monitores(monitores, "detalle"))
                
                responder_callback(callback_id)
                return "OK", 200
            
            if data_callback == "menu_add":
                user_states[chat_id] = "esperando_url"
                texto = "➕ <b>AGREGAR WEB</b>\n\nEscribe la URL completa (ej: https://ejemplo.com):"
                editar_mensaje(chat_id, message_id, texto, teclado_cancelar())
                responder_callback(callback_id)
                return "OK", 200
            
            if data_callback == "menu_delete":
                enviar_accion_escribiendo(chat_id)
                monitores = obtener_monitores()
                
                if not monitores:
                    texto = "❌ No hay webs para eliminar"
                    editar_mensaje(chat_id, message_id, texto, teclado_principal())
                else:
                    texto = "❌ <b>SELECCIONA WEB A ELIMINAR</b>"
                    editar_mensaje(chat_id, message_id, texto, teclado_monitores(monitores, "eliminar"))
                
                responder_callback(callback_id)
                return "OK", 200
            
            if data_callback == "menu_edit":
                enviar_accion_escribiendo(chat_id)
                monitores = obtener_monitores()
                
                if not monitores:
                    texto = "✏️ No hay webs para editar"
                    editar_mensaje(chat_id, message_id, texto, teclado_principal())
                else:
                    texto = "✏️ <b>SELECCIONA WEB A EDITAR</b>"
                    editar_mensaje(chat_id, message_id, texto, teclado_monitores(monitores, "editar"))
                
                responder_callback(callback_id)
                return "OK", 200
            
            if data_callback == "menu_metrics":
                enviar_accion_escribiendo(chat_id)
                monitores = obtener_monitores()
                
                if not monitores:
                    texto = "📊 No hay webs para ver métricas"
                    editar_mensaje(chat_id, message_id, texto, teclado_principal())
                else:
                    texto = "📊 <b>SELECCIONA WEB PARA VER MÉTRICAS</b>"
                    editar_mensaje(chat_id, message_id, texto, teclado_monitores(monitores, "metrics"))
                
                responder_callback(callback_id)
                return "OK", 200
            
            if data_callback == "menu_isup":
                user_states[chat_id] = "esperando_verificar"
                texto = "🔄 <b>VERIFICAR WEB</b>\n\nEscribe la URL a comprobar (ej: https://google.com):"
                editar_mensaje(chat_id, message_id, texto, teclado_cancelar())
                responder_callback(callback_id)
                return "OK", 200
            
            # ===== SELECCIÓN DE MONITOR CON ACCIÓN =====
            if data_callback.startswith('monitor_'):
                partes = data_callback.split('_')
                if len(partes) >= 3:
                    monitor_id = partes[1]
                    accion = partes[2]
                    
                    # Obtener detalles del monitor
                    monitores = obtener_monitores()
                    monitor = next((m for m in monitores if str(m['id']) == monitor_id), None)
                    
                    if not monitor:
                        editar_mensaje(chat_id, message_id, "❌ Monitor no encontrado", teclado_principal())
                        responder_callback(callback_id)
                        return "OK", 200
                    
                    if accion == "detalle":
                        estado = obtener_estado_texto(monitor['status'])
                        uptime = monitor.get('custom_uptime_ratio', 'N/A')
                        
                        texto = f"""📋 <b>DETALLE DEL MONITOR</b>

<b>Nombre:</b> {monitor['friendly_name']}
<b>URL:</b> {monitor['url']}
<b>Estado:</b> {estado}
<b>Uptime (30d):</b> {uptime}%
<b>Tipo:</b> {'HTTP(s)' if monitor['type'] == 1 else 'Ping' if monitor['type'] == 3 else 'Puerto'}
<b>Intervalo:</b> {monitor['interval']} segundos"""
                        
                        editar_mensaje(chat_id, message_id, texto, 
                                     teclado_acciones_monitor(monitor_id, monitor['friendly_name']))
                    
                    elif accion == "eliminar":
                        user_states[chat_id] = f"confirmar_eliminar_{monitor_id}"
                        texto = f"❌ ¿Estás seguro de eliminar <b>{monitor['friendly_name']}</b>?"
                        keyboard = {
                            "inline_keyboard": [
                                [{"text": "✅ SÍ, ELIMINAR", "callback_data": f"confirm_delete_{monitor_id}"}],
                                [{"text": "❌ NO, CANCELAR", "callback_data": "menu_delete"}]
                            ]
                        }
                        editar_mensaje(chat_id, message_id, texto, keyboard)
                    
                    elif accion == "editar":
                        texto = f"✏️ Función de edición en desarrollo para <b>{monitor['friendly_name']}</b>"
                        editar_mensaje(chat_id, message_id, texto, teclado_principal())
                    
                    elif accion == "metrics":
                        tiempos = monitor.get('response_times', [])
                        if tiempos:
                            ultimos = tiempos[:5]
                            texto = f"📊 <b>MÉTRICAS - {monitor['friendly_name']}</b>\n\n"
                            for t in ultimos:
                                fecha = datetime.datetime.fromtimestamp(t['datetime']).strftime('%d/%m %H:%M')
                                texto += f"• {fecha}: {t['value']}ms\n"
                        else:
                            texto = f"📊 No hay métricas disponibles para {monitor['friendly_name']}"
                        
                        editar_mensaje(chat_id, message_id, texto, teclado_principal())
                    
                    responder_callback(callback_id)
                    return "OK", 200
            
            # ===== ACCIONES SOBRE MONITOR =====
            if data_callback.startswith('pause_'):
                monitor_id = data_callback.replace('pause_', '')
                result = pausar_monitor(monitor_id)
                
                if result.get('stat') == 'ok':
                    texto = "⏸️ Monitor pausado correctamente"
                else:
                    texto = f"❌ Error: {result.get('error', {}).get('message', 'Desconocido')}"
                
                editar_mensaje(chat_id, message_id, texto, teclado_principal())
                responder_callback(callback_id)
                return "OK", 200
            
            if data_callback.startswith('resume_'):
                monitor_id = data_callback.replace('resume_', '')
                result = reanudar_monitor(monitor_id)
                
                if result.get('stat') == 'ok':
                    texto = "▶️ Monitor reanudado correctamente"
                else:
                    texto = f"❌ Error: {result.get('error', {}).get('message', 'Desconocido')}"
                
                editar_mensaje(chat_id, message_id, texto, teclado_principal())
                responder_callback(callback_id)
                return "OK", 200
            
            if data_callback.startswith('confirm_delete_'):
                monitor_id = data_callback.replace('confirm_delete_', '')
                result = eliminar_monitor(monitor_id)
                
                if result.get('stat') == 'ok':
                    texto = "✅ Monitor eliminado correctamente"
                else:
                    texto = f"❌ Error: {result.get('error', {}).get('message', 'Desconocido')}"
                
                editar_mensaje(chat_id, message_id, texto, teclado_principal())
                user_states.pop(chat_id, None)
                responder_callback(callback_id)
                return "OK", 200
            
            responder_callback(callback_id)
            return "OK", 200
        
        # ========== MENSAJES DE TEXTO ==========
        if 'message' in data:
            chat_id = data['message']['chat']['id']
            text = data['message'].get('text', '')
            user = data['message']['from'].get('first_name', 'Usuario')
            
            logger.info(f"💬 Mensaje: '{text}' de {user}")
            
            # Mostrar "escribiendo..."
            enviar_accion_escribiendo(chat_id)
            
            # Verificar si el usuario está en un estado de espera
            estado = user_states.get(chat_id)
            
            if estado == "esperando_url":
                # Crear monitor con la URL proporcionada
                result = crear_monitor(text)
                
                if result.get('stat') == 'ok':
                    monitor_id = result.get('monitor', {}).get('id')
                    enviar_mensaje(chat_id, 
                        f"✅ ¡Web agregada correctamente!\n\nID: {monitor_id}\nURL: {text}", 
                        teclado_principal())
                else:
                    error = result.get('error', {}).get('message', 'Error desconocido')
                    enviar_mensaje(chat_id, f"❌ Error al agregar: {error}", teclado_principal())
                
                user_states.pop(chat_id, None)
                
            elif estado == "esperando_verificar":
                # Verificar web directamente
                resultado = verificar_web_directa(text)
                
                if resultado['online']:
                    texto = f"""🟢 <b>WEB ONLINE</b>

<b>URL:</b> {text}
<b>Estado HTTP:</b> {resultado['status_code']}
<b>Tiempo respuesta:</b> {resultado['response_time']}ms
✅ La web está accesible"""
                else:
                    texto = f"""🔴 <b>WEB CAÍDA O INACCESIBLE</b>

<b>URL:</b> {text}
<b>Error:</b> {resultado['error']}
❌ No se pudo conectar a la web"""
                
                enviar_mensaje(chat_id, texto, teclado_principal())
                user_states.pop(chat_id, None)
                
            elif text == '/start':
                enviar_mensaje(chat_id, 
                    f"🎉 ¡Hola {user}! Soy <b>UptimeRobot Bot</b>\n\n"
                    f"Puedo monitorear tus webs y notificarte si caen.\n\n"
                    f"Selecciona una opción del menú:", teclado_principal())
            
            elif text == '/help':
                enviar_mensaje(chat_id, "Usa los botones del menú principal", teclado_principal())
            
            else:
                enviar_mensaje(chat_id, 
                    "❓ Comando no reconocido. Usa los botones del menú.", 
                    teclado_principal())
        
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
    
    logger.info(f"🚀 Bot UptimeRobot iniciado en puerto {PORT}")
    app.run(host='0.0.0.0', port=PORT)