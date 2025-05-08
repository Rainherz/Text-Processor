import threading
import time
import os
from urllib.parse import urlparse
import amqpstorm
from amqpstorm import Message
import logging
import datetime

# Configurar logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("servidor")

# Configuración de CloudAMQP
CLOUDAMQP_URL = os.environ.get('CLOUDAMQP_URL', 'amqps://tnluigbk:x9gWN83qzJ3CIZjiKKAyg327wKNb9eA1@porpoise.rmq.cloudamqp.com/tnluigbk')
url = urlparse(CLOUDAMQP_URL)

# Extraer componentes de la URL
RABBIT_HOST = url.hostname
RABBIT_USER = url.username
RABBIT_PASSWORD = url.password
RABBIT_VHOST = url.path[1:] if url.path else '%2f'
RABBIT_PORT = 5671  # Puerto para TLS
RABBIT_SSL = True   # Habilitar SSL para conexión segura
RPC_QUEUE = 'rpc_queue'
HEARTBEAT_INTERVAL = 30  # Reducir el intervalo de heartbeat a 30 segundos

# Estado global
SERVER_STATUS = {
    "running": False,
    "processed_messages": 0,
    "errors": 0,
    "last_error": None,
    "last_reconnect": None
}

# Clase de Servidor RPC mejorada
class TextProcessingServer(object):
    def __init__(self, host, username, password, rpc_queue, vhost, port=5671, ssl=True, heartbeat=30):
        self.host = host
        self.username = username
        self.password = password
        self.rpc_queue = rpc_queue
        self.vhost = vhost
        self.port = port
        self.ssl = ssl
        self.heartbeat = heartbeat
        self.connection = None
        self.channel = None
        self.should_reconnect = True
        self.heartbeat_thread = None
        
    def start(self):
        """Iniciar servidor con manejo de errores"""
        while self.should_reconnect:
            try:
                logger.info(f"Conectando a RabbitMQ: {self.host}:{self.port}")
                # Crear conexión con heartbeat reducido
                self.connection = amqpstorm.Connection(
                    self.host, 
                    self.username,
                    self.password,
                    virtual_host=self.vhost,
                    port=self.port,
                    ssl=self.ssl,
                    heartbeat=self.heartbeat
                )
                
                # Crear canal
                self.channel = self.connection.channel()
                
                # Declarar cola
                self.channel.queue.declare(self.rpc_queue)
                
                # Configurar QoS
                self.channel.basic.qos(prefetch_count=1)
                
                # Iniciar hilo de heartbeat
                self._create_heartbeat_thread()
                
                # Configurar consumidor
                self.channel.basic.consume(self._process_request, self.rpc_queue)
                
                logger.info(f"Iniciado. Esperando mensajes en '{self.rpc_queue}'")
                SERVER_STATUS["running"] = True
                SERVER_STATUS["last_reconnect"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # Iniciar consumo
                self.channel.start_consuming()
                
            except KeyboardInterrupt:
                logger.info("Detenido por el usuario")
                self.should_reconnect = False
                break
                
            except Exception as e:
                SERVER_STATUS["running"] = False
                SERVER_STATUS["errors"] += 1
                SERVER_STATUS["last_error"] = str(e)
                logger.error(f"Error: {str(e)}")
                
                # Limpiar conexiones
                try:
                    if self.connection:
                        self.connection.close()
                except:
                    pass
                    
                # Esperar antes de reconectar
                logger.info("Esperando para reconectar...")
                time.sleep(5)
                
    def _create_heartbeat_thread(self):
        """Crear hilo para enviar heartbeats"""
        if self.heartbeat_thread and self.heartbeat_thread.is_alive():
            return
            
        self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop)
        self.heartbeat_thread.daemon = True
        self.heartbeat_thread.start()
                
    def _heartbeat_loop(self):
        """Mantener la conexión viva enviando un comando liviano periódicamente"""
        while self.should_reconnect:
            try:
                if self.connection and self.connection.is_open:
                    # En lugar de send_heartbeat(), usamos un comando liviano
                    # para mantener la conexión activa
                    self.channel.basic.publish(
                        body='',
                        exchange='',
                        routing_key='',
                        properties={
                            'delivery_mode': 1  # No persistente
                        }
                    )
            except Exception as e:
                SERVER_STATUS["errors"] += 1
                SERVER_STATUS["last_error"] = f"Servidor heartbeat error: {str(e)}"
                logger.error(f"Error en heartbeat: {str(e)}")
                
            # Dormir por menos tiempo que el intervalo de heartbeat
            time.sleep(self.heartbeat // 2)
        
    def _process_request(self, message):
        """Procesar solicitudes con manejo de errores"""
        try:
            # Extraer payload
            payload = message.body
            logger.info(f"Solicitud recibida: {payload}")
            
            # Procesar texto
            response = self._process_text(payload)
            
            # Crear respuesta
            response_message = Message.create(
                message.channel,
                response
            )
            
            # Configurar propiedades
            response_message.correlation_id = message.correlation_id
            response_message.properties['delivery_mode'] = 2
            
            # Publicar respuesta
            response_message.publish(routing_key=message.reply_to)
            logger.info(f"Respuesta enviada: {response}")
            
            # Confirmar mensaje
            message.ack()
            
            # Actualizar estadísticas
            SERVER_STATUS["processed_messages"] += 1
            
        except Exception as e:
            SERVER_STATUS["errors"] += 1
            SERVER_STATUS["last_error"] = str(e)
            logger.error(f"Error procesando solicitud: {str(e)}")
            
            # Intentar confirmar el mensaje
            try:
                message.ack()
            except:
                pass
        
    def _process_text(self, payload):
        """Procesar texto según comando"""
        try:
            # Dividir payload
            parts = payload.split(':', 1)
            
            if len(parts) < 2:
                return "ERROR: Formato inválido. Se espera 'comando:texto'"
            
            comando = parts[0].lower()
            texto = parts[1]
            
            # Procesar según comando
            if comando == "mayusculas":
                return texto.upper()
            elif comando == "minusculas":
                return texto.lower()
            elif comando == "invertir":
                return texto[::-1]
            elif comando == "longitud":
                return str(len(texto))
            elif comando == "capitalizar":
                return texto.capitalize()
            elif comando == "titulo":
                return texto.title()
            elif comando == "intercambiar_caso":
                return texto.swapcase()
            elif comando == "contar_palabras":
                return str(len(texto.split()))
            elif comando == "recortar":
                return texto.strip()
            elif comando == "ayuda":
                return "Comandos disponibles: mayusculas, minusculas, invertir, longitud, capitalizar, titulo, intercambiar_caso, contar_palabras, recortar"
            else:
                return f"ERROR: Comando desconocido '{comando}'"
        except Exception as e:
            return f"ERROR: {str(e)}"

# Lista de operaciones disponibles (para referencia)
TEXT_OPERATIONS = [
    {"id": "mayusculas", "name": "Convertir a MAYÚSCULAS", "icon": "arrow-up-square", "description": "Convierte todo el texto a mayúsculas"},
    {"id": "minusculas", "name": "Convertir a minúsculas", "icon": "arrow-down-square", "description": "Convierte todo el texto a minúsculas"},
    {"id": "invertir", "name": "Invertir texto", "icon": "arrow-left-right", "description": "Invierte el orden de los caracteres del texto"},
    {"id": "longitud", "name": "Longitud del texto", "icon": "rulers", "description": "Cuenta el número de caracteres en el texto"},
    {"id": "capitalizar", "name": "Capitalizar", "icon": "type-bold", "description": "Convierte a mayúscula la primera letra del texto"},
    {"id": "titulo", "name": "Formato título", "icon": "card-heading", "description": "Convierte a mayúscula la primera letra de cada palabra"},
    {"id": "intercambiar_caso", "name": "Intercambiar caso", "icon": "arrow-down-up", "description": "Invierte mayúsculas/minúsculas"},
    {"id": "contar_palabras", "name": "Contar palabras", "icon": "list-ol", "description": "Cuenta el número de palabras en el texto"},
    {"id": "recortar", "name": "Recortar espacios", "icon": "scissors", "description": "Elimina espacios al inicio y final del texto"}
]

# Variable global para servidor
SERVER_INSTANCE = None
SERVER_THREAD = None

def init_server():
    """Iniciar servidor RPC"""
    global SERVER_INSTANCE, SERVER_THREAD
    
    logger.info("Iniciando servidor RPC...")
    
    # Detener servidor existente
    if SERVER_INSTANCE and hasattr(SERVER_INSTANCE, 'should_reconnect'):
        SERVER_INSTANCE.should_reconnect = False
    
    if SERVER_THREAD and SERVER_THREAD.is_alive():
        logger.info("Esperando que el servidor anterior se detenga...")
        time.sleep(3)  # Dar tiempo para que el hilo anterior se detenga
    
    # Crear nuevo servidor
    SERVER_INSTANCE = TextProcessingServer(
        RABBIT_HOST, 
        RABBIT_USER, 
        RABBIT_PASSWORD, 
        RPC_QUEUE,
        RABBIT_VHOST,
        RABBIT_PORT,
        RABBIT_SSL,
        HEARTBEAT_INTERVAL
    )
    
    # Crear e iniciar hilo de servidor
    SERVER_THREAD = threading.Thread(target=lambda: SERVER_INSTANCE.start())
    SERVER_THREAD.daemon = True
    SERVER_THREAD.start()
    
    # Esperar un momento para que el servidor se inicie
    time.sleep(2)
    
    logger.info(f"Servidor iniciado en hilo separado. Estado: {SERVER_STATUS['running']}")
    return SERVER_STATUS['running']

def get_server_status():
    """Obtener estado del servidor"""
    return SERVER_STATUS

# Si se ejecuta directamente, iniciar servidor
if __name__ == "__main__":
    init_server()
    
    # Mantener proceso vivo
    try:
        while True:
            time.sleep(10)
            logger.info(f"Servidor activo. Estado: {get_server_status()}")
    except KeyboardInterrupt:
        logger.info("Deteniendo servidor...")
        if SERVER_INSTANCE:
            SERVER_INSTANCE.should_reconnect = False
