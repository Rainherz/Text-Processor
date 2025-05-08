import logging
import threading
import time
import os
from cliente import init_client, get_client_status
from server import init_server, get_server_status
from app import app

# Configurar logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("wsgi")

def init_services():
    """Inicializar servicios con reintentos"""
    max_retries = 5
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            logger.info(f"Intento {retry_count + 1} de iniciar servicios...")
            
            # Iniciar servidor
            server_ok = init_server()
            logger.info(f"Estado del servidor: {'OK' if server_ok else 'ERROR'}")
            
            # Iniciar cliente
            client_ok = init_client()
            logger.info(f"Estado del cliente: {'OK' if client_ok else 'ERROR'}")
            
            if server_ok and client_ok:
                logger.info("¡Servicios iniciados correctamente!")
                return True
            
            logger.warning("No se pudieron iniciar todos los servicios, reintentando...")
        except Exception as e:
            logger.error(f"Error al iniciar servicios: {str(e)}")
        
        # Incrementar contador y esperar antes de reintentar
        retry_count += 1
        time.sleep(5)
    
    logger.error("No se pudieron iniciar los servicios después de varios intentos")
    return False

# Iniciar servicios en un hilo separado
def start_services_delayed():
    # Esperar un momento antes de iniciar
    time.sleep(2)
    # Iniciar servicios
    init_services()

# Crear e iniciar hilo
startup_thread = threading.Thread(target=start_services_delayed)
startup_thread.daemon = True
startup_thread.start()

# Este es el punto de entrada para gunicorn
if __name__ == "__main__":
    # Para desarrollo local
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
