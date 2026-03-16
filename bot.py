import os
import logging
import sys
from flask import Flask, request
import requests
import json
import psutil
import platform
import datetime
import threading
import time
from collections import defaultdict

# ============================================
# CONFIGURACIÓN
# ============================================
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
PORT = int(os.environ.get('PORT', 10000))

# API Key de UptimeRobot
UPTIMEROBOT_API_KEY = "u3358345-5c4ed5db967b687a061c90e0"
UPTIMEROBOT_API_URL = "https://api.uptimerobot.com/v2"

# Usuario autorizado (SOLO este usuario puede usar el bot)
AUTORIZADO = "@nautaii"  # O también puedes usar el ID numérico

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

# Configuración de notificaciones por usuario
notificaciones_config = defaultdict(lambda: {
    "activo": False,
    "intervalo": 10,  # minutos
    "ultima_notificacion": None,
    "webs_estado_anterior": {}
})

# Thread local para el loop de notificaciones
notificaciones_thread_running = True

# ============================================
# FUNCIONES DE SEGURIDAD - SOLO USUARIO AUTORIZADO
# ============================================

def usuario_autorizado(username):
    """Verifica si el usuario está autorizado"""
    return username == AUTORIZADO

def verificar_acceso(update):
    """Verifica acceso y envía mensaje si no autorizado"""
    if 'message' in update:
        username = update['message']['from'].get('username', '')
        chat_id = update['message']['chat']['id']
    elif 'callback_query' in update:
        username = update['callback_query']['from'].get('username', '')
        chat_id = update['callback_query']['message']['chat']['id']
    else:
        return False, None
    
    if not usuario_autorizado(f"@{username}"):
        enviar_mensaje(chat_id, "⛔ <b>ACCESO DENEGADO</b>\n\nEste bot es privado y solo puede ser usado por @nautaii.")
        return False, None
    
    return True, chat_id

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
    """Crea un nuevo monitor"""
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

# ============================================
# FUNCIONES DE NOTIFICACIONES AUTOMÁTICAS
# ============================================

def verificar_cambios_estado():
    """Verifica si alguna web cambió de estado y envía notificación"""
    try:
        monitores = obtener_monitores()
        if not monitores:
            return
        
        # Obtener el chat_id del usuario autorizado (simplificado - asumimos que ya inició el bot)
        # En un bot real, deberías almacenar el chat_id cuando el usuario interactúa
        # Por ahora, usaremos un valor fijo o lo obtendremos de la configuración
        chat_id = None
        
        # Buscar el chat_id en la configuración (si existe una notificación activa)
        for user_id, config in notificaciones_config.items():
            if config["activo"]:
                chat_id = user_id
                break
        
        if not chat_id:
            return
        
        # Crear diccionario de estado actual
        estado_actual = {}
        for m in monitores:
            estado_actual[m['id']] = {
                "nombre": m['friendly_name'],
                "estado": m['status'],
                "url": m['url']
            }
        
        # Comparar con estado anterior
        estado_anterior = notificaciones_config[chat_id]["webs_estado_anterior"]
        
        cambios = []
        for monitor_id, datos in estado_actual.items():
            estado_previo = estado_anterior.get(monitor_id, {}).get("estado")
            
            if estado_previo is not None and estado_previo != datos["estado"]:
                # Hubo cambio de estado
                estado_actual_texto = obtener_estado_texto(datos["estado"])
                estado_previo_texto = obtener_estado_texto(estado_previo)
                
                cambios.append(f"""🔔 <b>¡CAMBIO DE ESTADO!</b>

<b>Web:</b> {datos['nombre']}
<b>URL:</b> {datos['url']}
<b>Cambió de:</b> {estado_previo_texto}
<b>a:</b> {estado_actual_texto}
<b>Hora:</b> {datetime.datetime.now().strftime('%d/%m %H:%M:%S')}
""")
        
        # Enviar notificaciones si hay cambios
        if cambios:
            for cambio in cambios:
                enviar_mensaje(chat_id, cambio)
        
        # Actualizar estado anterior
        notificaciones_config[chat_id]["webs_estado_anterior"] = estado_actual
        
    except Exception as e:
        logger.error(f"Error en verificar_cambios_estado: {e}")

def enviar_notificaciones_periodicas():
    """Función que se ejecuta en un thread para enviar notificaciones periódicas"""
    global notificaciones_thread_running
    
    while notificaciones_thread_running:
        try:
            # Verificar cambios de estado para cada usuario con notificaciones activas
            for chat_id, config in notificaciones_config.items():
                if config["activo"]:
                    # Verificar si ya pasó el intervalo
                    ultima = config["ultima_notificacion"]
                    ahora = datetime.datetime.now()
                    
                    if ultima is None or (ahora - ultima).total_seconds() >= config["intervalo"] * 60:
                        # Enviar notificación de estado general
                        monitores = obtener_monitores()
                        if monitores:
                            # Contar estados
                            estados = {"🟢": 0, "🔴": 0, "🟠": 0, "⚪": 0}
                            for m in monitores:
                                color = obtener_color_estado(m['status'])
                                estados[color] += 1
                            
                            mensaje = f"""📊 <b>REPORTE PERIÓDICO</b> ({config['intervalo']} min)

<b>Resumen general:</b>
🟢 OK: {estados['🟢']}
🔴 Caídos: {estados['🔴']}
🟠 Inestables: {estados['🟠']}
⚪ Pausados: {estados['⚪']}

<b>Total monitoreados:</b> {len(monitores)}
<b>Hora:</b> {ahora.strftime('%d/%m %H:%M:%S')}"""
                            
                            enviar_mensaje(chat_id, mensaje)
                            
                            # Verificar cambios específicos
                            verificar_cambios_estado()
                        
                        notificaciones_config[chat_id]["ultima_notificacion"] = ahora
            
            # Esperar 30 segundos antes de la próxima verificación
            time.sleep(30)
            
        except Exception as e:
            logger.error(f"Error en thread de notificaciones: {e}")
            time.sleep(60)

def autoping():
    """Función que envía un ping al usuario cada 20 minutos"""
    global notificaciones_thread_running
    
    while notificaciones_thread_running:
        try:
            # Buscar el chat_id del usuario autorizado
            chat_id = None
            for user_id in notificaciones_config.keys():
                chat_id = user_id
                break
            
            if chat_id:
                ahora = datetime.datetime.now()
                mensaje = f"🔄 <b>AUTOPING</b>\n\nEl bot sigue activo.\nHora: {ahora.strftime('%d/%m %H:%M:%S')}"
                enviar_mensaje(chat_id, mensaje)
            
            # Esperar 20 minutos
            time.sleep(1200)  # 20 minutos en segundos
            
        except Exception as e:
            logger.error(f"Error en autoping: {e}")
            time.sleep(1200)

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
                {"text": "❌ ELIMINAR", "callback_data": "menu_delete"},
                {"text": "⏸️ PAUSAR/REANUDAR", "callback_data": "menu_pause_resume"}
            ],
            [
                {"text": "🔔 NOTIFICACIONES", "callback_data": "menu_notificaciones"},
                {"text": "🖥️ SISTEMA", "callback_data": "menu_sysinfo"}
            ],
            [
                {"text": "🔄 VERIFICAR AHORA", "callback_data": "menu_verificar_ahora"},
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

def teclado_notificaciones(chat_id):
    """Teclado para configuración de notificaciones"""
    config = notificaciones_config[chat_id]
    estado = "✅ ACTIVADAS" if config["activo"] else "❌ DESACTIVADAS"
    
    return {
        "inline_keyboard": [
            [{"text": f"🔔 Notificaciones: {estado}", "callback_data": "notif_toggle"}],
            [{"text": f"⏱️ Intervalo: {config['intervalo']} min", "callback_data": "notif_intervalo"}],
            [
                {"text": "➕ 1 min", "callback_data": "notif_+1"},
                {"text": "➕ 5 min", "callback_data": "notif_+5"},
                {"text": "➖ 1 min", "callback_data": "notif_-1"}
            ],
            [
                {"text": "10 min", "callback_data": "notif_10"},
                {"text": "30 min", "callback_data": "notif_30"},
                {"text": "60 min", "callback_data": "notif_60"}
            ],
            [{"text": "🏠 VOLVER", "callback_data": "menu_inicio"}]
        ]
    }

def teclado_monitores(monitores, accion="seleccionar"):
    """Crea teclado con lista de monitores"""
    keyboard = []
    for m in monitores[:10]:
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

🔔 <b>Notificaciones:</b> {'Activas' if notificaciones_config.get(chat_id_global, {}).get('activo') else 'Inactivas'}
"""

# ============================================
# PROCESAR COMANDOS Y CALLBACKS
# ============================================

chat_id_global = None  # Para almacenar el chat_id del usuario autorizado

@app.route('/', methods=['GET'])
def home():
    return "Bot UptimeRobot Privado - Activo"

@app.route('/health', methods=['GET'])
def health():
    return "OK", 200

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    global chat_id_global
    
    try:
        data = request.get_json()
        
        # ========== VERIFICAR ACCESO ==========
        acceso, chat_id = verificar_acceso(data)
        if not acceso:
            return "OK", 200
        
        # Guardar chat_id para notificaciones
        chat_id_global = chat_id
        if chat_id not in notificaciones_config:
            notificaciones_config[chat_id] = {
                "activo": False,
                "intervalo": 10,
                "ultima_notificacion": None,
                "webs_estado_anterior": {}
            }
        
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
            
            # ===== NOTIFICACIONES =====
            if data_callback == "menu_notificaciones":
                editar_mensaje(chat_id, message_id, 
                    "🔔 <b>CONFIGURACIÓN DE NOTIFICACIONES</b>\n\n"
                    "• Recibirás reportes periódicos del estado de tus webs\n"
                    "• También notificaciones cuando una web cambie de estado",
                    teclado_notificaciones(chat_id))
                responder_callback(callback_id)
                return "OK", 200
            
            if data_callback == "notif_toggle":
                config = notificaciones_config[chat_id]
                config["activo"] = not config["activo"]
                if config["activo"]:
                    config["ultima_notificacion"] = datetime.datetime.now()
                    texto = "✅ Notificaciones activadas"
                else:
                    texto = "❌ Notificaciones desactivadas"
                
                editar_mensaje(chat_id, message_id, texto, teclado_notificaciones(chat_id))
                responder_callback(callback_id)
                return "OK", 200
            
            if data_callback == "notif_intervalo":
                texto = f"⏱️ Intervalo actual: {notificaciones_config[chat_id]['intervalo']} minutos"
                responder_callback(callback_id, texto, mostrar_alerta=True)
                return "OK", 200
            
            if data_callback in ["notif_+1", "notif_+5", "notif_-1"]:
                config = notificaciones_config[chat_id]
                if data_callback == "notif_+1":
                    config["intervalo"] = min(config["intervalo"] + 1, 1440)
                elif data_callback == "notif_+5":
                    config["intervalo"] = min(config["intervalo"] + 5, 1440)
                elif data_callback == "notif_-1":
                    config["intervalo"] = max(config["intervalo"] - 1, 1)
                
                editar_mensaje(chat_id, message_id, 
                    f"✅ Intervalo actualizado a {config['intervalo']} minutos",
                    teclado_notificaciones(chat_id))
                responder_callback(callback_id)
                return "OK", 200
            
            if data_callback in ["notif_10", "notif_30", "notif_60"]:
                config = notificaciones_config[chat_id]
                if data_callback == "notif_10":
                    config["intervalo"] = 10
                elif data_callback == "notif_30":
                    config["intervalo"] = 30
                elif data_callback == "notif_60":
                    config["intervalo"] = 60
                
                editar_mensaje(chat_id, message_id, 
                    f"✅ Intervalo actualizado a {config['intervalo']} minutos",
                    teclado_notificaciones(chat_id))
                responder_callback(callback_id)
                return "OK", 200
            
            if data_callback == "menu_verificar_ahora":
                enviar_accion_escribiendo(chat_id)
                verificar_cambios_estado()
                responder_callback(callback_id, "✅ Verificación completada", mostrar_alerta=True)
                return "OK", 200
            
            if data_callback == "menu_help":
                ayuda = """<b>❓ AYUDA - UptimeRobot Bot Privado</b>

<b>📋 COMANDOS DISPONIBLES:</b>

➕ <b>AGREGAR WEB</b> - Añade un sitio a monitorear
📋 <b>ESTADO</b> - Ver estado de todas tus webs
❌ <b>ELIMINAR</b> - Eliminar un monitor
⏸️ <b>PAUSAR/REANUDAR</b> - Pausar o reanudar monitoreo
🔔 <b>NOTIFICACIONES</b> - Configurar alertas automáticas
🖥️ <b>SISTEMA</b> - Info del servidor
🔄 <b>VERIFICAR AHORA</b> - Forzar verificación de cambios

<b>🔹 NOTIFICACIONES AUTOMÁTICAS:</b>
• Reportes periódicos cada X minutos (configurable)
• Alertas cuando una web cambia de estado
• Autoping cada 20 minutos para confirmar que el bot vive

<b>🔒 SEGURIDAD:</b>
• Bot privado - Solo @nautaii puede usarlo

<b>📊 ESTADOS:</b>
🟢 Activo   🔴 Caído   🟠 Inestable   ⚪ Pausado"""
                
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
                    texto = "📋 <b>TUS WEBS MONITOREADAS</b>\n\nSelecciona una para ver acciones:"
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
            
            if data_callback == "menu_pause_resume":
                enviar_accion_escribiendo(chat_id)
                monitores = obtener_monitores()
                
                if not monitores:
                    texto = "⏸️ No hay webs para pausar/reanudar"
                    editar_mensaje(chat_id, message_id, texto, teclado_principal())
                else:
                    texto = "⏸️ <b>SELECCIONA WEB PARA PAUSAR/REANUDAR</b>"
                    editar_mensaje(chat_id, message_id, texto, teclado_monitores(monitores, "pausar"))
                
                responder_callback(callback_id)
                return "OK", 200
            
            # ===== SELECCIÓN DE MONITOR =====
            if data_callback.startswith('monitor_'):
                partes = data_callback.split('_')
                if len(partes) >= 3:
                    monitor_id = partes[1]
                    accion = partes[2]
                    
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
<b>Intervalo:</b> {monitor['interval']} segundos"""
                        
                        editar_mensaje(chat_id, message_id, texto, 
                                     teclado_acciones_monitor(monitor_id, monitor['friendly_name']))
                    
                    elif accion in ["eliminar", "pausar"]:
                        if accion == "eliminar":
                            user_states[chat_id] = f"confirmar_eliminar_{monitor_id}"
                            texto = f"❌ ¿Estás seguro de eliminar <b>{monitor['friendly_name']}</b>?"
                        else:
                            user_states[chat_id] = f"confirmar_pausar_{monitor_id}"
                            texto = f"⏸️ ¿Qué acción deseas para <b>{monitor['friendly_name']}</b>?"
                        
                        keyboard = {
                            "inline_keyboard": [
                                [{"text": "✅ CONFIRMAR", "callback_data": f"confirm_{accion}_{monitor_id}"}],
                                [{"text": "❌ CANCELAR", "callback_data": f"menu_{accion}"}]
                            ]
                        }
                        editar_mensaje(chat_id, message_id, texto, keyboard)
                    
                    responder_callback(callback_id)
                    return "OK", 200
            
            # ===== ACCIONES SOBRE MONITOR =====
            if data_callback.startswith('confirm_eliminar_'):
                monitor_id = data_callback.replace('confirm_eliminar_', '')
                result = eliminar_monitor(monitor_id)
                
                if result.get('stat') == 'ok':
                    texto = "✅ Monitor eliminado correctamente"
                else:
                    texto = f"❌ Error: {result.get('error', {}).get('message', 'Desconocido')}"
                
                editar_mensaje(chat_id, message_id, texto, teclado_principal())
                user_states.pop(chat_id, None)
                responder_callback(callback_id)
                return "OK", 200
            
            if data_callback.startswith('confirm_pausar_'):
                monitor_id = data_callback.replace('confirm_pausar_', '')
                # Aquí deberías mostrar opciones de pausar/reanudar
                texto = "Función de pausar/reanudar - Usa los botones del menú principal"
                editar_mensaje(chat_id, message_id, texto, teclado_principal())
                responder_callback(callback_id)
                return "OK", 200
            
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
            
            responder_callback(callback_id)
            return "OK", 200
        
        # ========== MENSAJES DE TEXTO ==========
        if 'message' in data:
            chat_id = data['message']['chat']['id']
            text = data['message'].get('text', '')
            user = data['message']['from'].get('username', 'sin_username')
            
            logger.info(f"💬 Mensaje de @{user}: '{text}'")
            
            # Mostrar "escribiendo..."
            enviar_accion_escribiendo(chat_id)
            
            # Verificar si el usuario está en un estado de espera
            estado = user_states.get(chat_id)
            
            if estado == "esperando_url":
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
                
            elif text == '/start':
                enviar_mensaje(chat_id, 
                    f"🎉 ¡Bienvenido @{user}! (usuario autorizado)\n\n"
                    f"Soy <b>UptimeRobot Bot Privado</b>\n\n"
                    f"Puedo monitorear tus webs y notificarte automáticamente.\n\n"
                    f"Selecciona una opción del menú:", teclado_principal())
            
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
    # Iniciar thread de notificaciones
    notificaciones_thread = threading.Thread(target=enviar_notificaciones_periodicas, daemon=True)
    notificaciones_thread.start()
    
    # Iniciar thread de autoping
    autoping_thread = threading.Thread(target=autoping, daemon=True)
    autoping_thread.start()
    
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
    
    logger.info(f"🚀 Bot UptimeRobot Privado iniciado en puerto {PORT}")
    logger.info(f"👤 Usuario autorizado: {AUTORIZADO}")
    logger.info(f"🔄 Autoping cada 20 minutos")
    app.run(host='0.0.0.0', port=PORT)