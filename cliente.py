import threading
import time
import os
import datetime
import json
from urllib.parse import urlparse
import amqpstorm
from amqpstorm import Message
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("cliente")

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
CLIENT_STATUS = {
    "connected": False,
    "processed_messages": 0,
    "errors": 0,
    "last_error": None,
    "last_reconnect": None
}

# Clase de Cliente RPC mejorada
class RpcClient(object):
    def __init__(self, host, username, password, rpc_queue, vhost, port=5671, ssl=True, heartbeat=30):
        self.queue = {}
        self.host = host
        self.username = username
        self.password = password
        self.vhost = vhost
        self.port = port
        self.ssl = ssl
        self.heartbeat = heartbeat
        self.channel = None
        self.connection = None
        self.callback_queue = None
        self.rpc_queue = rpc_queue
        self.consumer_thread = None
        self.heartbeat_thread = None
        self.should_reconnect = True
        self.open()

    def open(self):
        """Abrir conexión con manejo de errores y reconexión"""
        if self.connection and self.connection.is_open:
            return True
        
        try:
            logger.info(f"Conectando a RabbitMQ: {self.host}:{self.port}")
            # Configurar conexión con tiempo de heartbeat reducido
            self.connection = amqpstorm.Connection(
                self.host, 
                self.username,
                self.password,
                virtual_host=self.vhost,
                port=self.port,
                ssl=self.ssl,
                heartbeat=self.heartbeat
            )
            
            self.channel = self.connection.channel()
            # Asegurar que la cola RPC exista
            self.channel.queue.declare(self.rpc_queue)
            
            # Crear cola de respuestas exclusiva
            result = self.channel.queue.declare(exclusive=True)
            self.callback_queue = result['queue']
            
            # Configurar consumidor
            self.channel.basic.consume(self._on_response, no_ack=True,
                                      queue=self.callback_queue)
            
            # Iniciar hilo de consumo
            self._create_process_thread()
            
            # Iniciar hilo de heartbeat
            self._create_heartbeat_thread()
            
            logger.info("Conectado exitosamente a RabbitMQ")
            CLIENT_STATUS["connected"] = True
            CLIENT_STATUS["last_reconnect"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            return True
        except Exception as e:
            CLIENT_STATUS["connected"] = False
            CLIENT_STATUS["errors"] += 1
            CLIENT_STATUS["last_error"] = str(e)
            logger.error(f"Error al conectar con RabbitMQ: {str(e)}")
            return False

    def _create_process_thread(self):
        """Crear hilo para procesar mensajes"""
        if self.consumer_thread and self.consumer_thread.is_alive():
            return
            
        self.consumer_thread = threading.Thread(target=self._process_data_events)
        self.consumer_thread.daemon = True
        self.consumer_thread.start()

    def _create_heartbeat_thread(self):
        """Crear hilo para enviar heartbeats"""
        if self.heartbeat_thread and self.heartbeat_thread.is_alive():
            return
            
        self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop)
        self.heartbeat_thread.daemon = True
        self.heartbeat_thread.start()

    def _process_data_events(self):
        """Procesar eventos con manejo de errores y reconexión"""
        while self.should_reconnect:
            try:
                if self.connection and self.connection.is_open:
                    self.channel.start_consuming(to_tuple=False)
            except Exception as e:
                CLIENT_STATUS["errors"] += 1
                CLIENT_STATUS["last_error"] = str(e)
                logger.error(f"Error en hilo de consumo: {str(e)}")
                CLIENT_STATUS["connected"] = False
                
                # Intentar reconectar
                time.sleep(5)  # Esperar antes de reconectar
                self._reconnect()

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
                CLIENT_STATUS["errors"] += 1
                CLIENT_STATUS["last_error"] = f"Heartbeat error: {str(e)}"
                logger.error(f"Error en heartbeat: {str(e)}")
                
                # Intentar reconectar si el error es de conexión
                if self.connection and not self.connection.is_open:
                    self._reconnect()
                
            # Dormir por menos tiempo que el intervalo de heartbeat
            time.sleep(self.heartbeat // 2)

    def _reconnect(self):
        """Intentar reconectar al servidor RabbitMQ"""
        if not self.should_reconnect:
            return
            
        logger.info("Intentando reconectar...")
        
        # Cerrar conexiones existentes
        try:
            if self.connection:
                self.connection.close()
        except:
            pass
            
        # Intentar reconectar
        self.open()

    def _on_response(self, message):
        """Manejar respuestas"""
        try:
            self.queue[message.correlation_id] = message.body
        except Exception as e:
            CLIENT_STATUS["errors"] += 1
            CLIENT_STATUS["last_error"] = str(e)
            logger.error(f"Error en manejador de respuestas: {str(e)}")

    def send_request(self, payload):
        """Enviar solicitud con manejo de errores"""
        try:
            # Verificar y reconectar si es necesario
            if not self.connection or not self.connection.is_open:
                if not self.open():
                    return None
                    
            # Crear mensaje
            message = Message.create(self.channel, payload)
            message.reply_to = self.callback_queue
            
            # Crear entrada en diccionario
            self.queue[message.correlation_id] = None
            
            # Publicar solicitud
            message.publish(routing_key=self.rpc_queue)
            
            return message.correlation_id
        except Exception as e:
            CLIENT_STATUS["errors"] += 1
            CLIENT_STATUS["last_error"] = str(e)
            logger.error(f"Error al enviar solicitud: {str(e)}")
            
            # Intentar reconectar
            self._reconnect()
            return None

    def is_connected(self):
        """Verificar conexión"""
        return self.connection and self.connection.is_open

    def close(self):
        """Cerrar conexión"""
        self.should_reconnect = False
        if self.connection:
            try:
                self.connection.close()
            except:
                pass
        CLIENT_STATUS["connected"] = False

# Variable global para el cliente RPC
RPC_CLIENT = None

def init_client():
    """Inicializar cliente RPC"""
    global RPC_CLIENT
    
    logger.info("Iniciando cliente RPC...")
    
    # Si ya existe una instancia, cerrarla primero
    if RPC_CLIENT:
        try:
            RPC_CLIENT.close()
        except:
            pass
    
    # Crear nueva instancia
    RPC_CLIENT = RpcClient(
        RABBIT_HOST, 
        RABBIT_USER, 
        RABBIT_PASSWORD, 
        RPC_QUEUE, 
        RABBIT_VHOST,
        RABBIT_PORT,
        RABBIT_SSL,
        HEARTBEAT_INTERVAL
    )
    
    logger.info(f"Cliente RPC inicializado. Conectado: {RPC_CLIENT.is_connected()}")
    return RPC_CLIENT.is_connected()

def get_client_status():
    """Obtener estado del cliente"""
    if RPC_CLIENT:
        CLIENT_STATUS["connected"] = RPC_CLIENT.is_connected()
    
    return CLIENT_STATUS

# Si se ejecuta directamente, iniciar cliente
if __name__ == "__main__":
    init_client()
    
    # Mantener proceso vivo
    try:
        while True:
            time.sleep(10)
            logger.info(f"Cliente activo. Estado: {get_client_status()}")
    except KeyboardInterrupt:
        logger.info("Deteniendo cliente...")
        if RPC_CLIENT:
            RPC_CLIENT.close()
