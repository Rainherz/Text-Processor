from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
import os
import datetime
import json
from time import sleep
import logging
import threading

# Importar cliente y servidor
from cliente import RPC_CLIENT, init_client, get_client_status
from server import TEXT_OPERATIONS, get_server_status, init_server

# Configurar logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("app")

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Función para guardar historial
def save_history(operation, input_text, result):
    if 'history' not in session:
        session['history'] = []
    
    history_item = {
        'timestamp': datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        'operation': operation,
        'input_text': input_text,
        'result': result
    }
    
    session['history'] = [history_item] + session['history'][:19]
    session.modified = True

# Rutas de la aplicación
@app.route('/')
def index():
    """Página principal"""
    client_status = get_client_status()
    server_status = get_server_status()
    connected = client_status["connected"] and server_status["running"]
    
    return render_template('index.html', 
                          operations=TEXT_OPERATIONS, 
                          connected=connected,
                          history=session.get('history', []))

@app.route('/about')
def about():
    """Página acerca de"""
    return render_template('about.html')

@app.route('/process', methods=['POST'])
def process_text():
    """Procesar texto vía RPC"""
    operation = request.form.get('operation')
    text = request.form.get('text')
    
    if not operation or not text:
        flash('Por favor, completa todos los campos', 'danger')
        return redirect(url_for('index'))
    
    # Verificar conexión
    if not RPC_CLIENT or not RPC_CLIENT.is_connected():
        # Intentar reconectar
        if not init_client():
            flash('Error: No se pudo conectar con el servidor RPC', 'danger')
            return redirect(url_for('index'))
    
    # Preparar payload
    payload = f"{operation}:{text}"
    
    # Enviar solicitud
    corr_id = RPC_CLIENT.send_request(payload)
    
    if not corr_id:
        flash('Error al enviar la solicitud', 'danger')
        return redirect(url_for('index'))
    
    # Esperar respuesta con timeout
    max_wait = 100  # 10 segundos
    counter = 0
    
    while counter < max_wait:
        if corr_id in RPC_CLIENT.queue and RPC_CLIENT.queue[corr_id] is not None:
            break
        sleep(0.1)
        counter += 1
    
    # Verificar timeout
    if counter >= max_wait or RPC_CLIENT.queue.get(corr_id) is None:
        flash('Tiempo de espera agotado. No se recibió respuesta del servidor', 'warning')
        return redirect(url_for('index'))
    
    # Obtener resultado
    result = RPC_CLIENT.queue[corr_id]
    
    # Obtener nombre de operación
    operation_name = operation
    for op in TEXT_OPERATIONS:
        if op['id'] == operation:
            operation_name = op['name']
            break
    
    # Guardar historial
    save_history(operation_name, text, result)
    
    # Responder según tipo de solicitud
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'success': True,
            'operation': operation_name,
            'result': result
        })
    
    flash(f'Operación completada: {operation_name}', 'success')
    return redirect(url_for('index'))

@app.route('/clear-history', methods=['POST'])
def clear_history():
    """Borrar historial"""
    session.pop('history', None)
    flash('Historial eliminado', 'info')
    return redirect(url_for('index'))

@app.route('/health')
def health_check():
    """Verificar salud"""
    client_status = get_client_status()
    server_status = get_server_status()
    
    return jsonify({
        'app': 'ok',
        'client_connected': client_status["connected"],
        'server_running': server_status["running"],
        'processed_messages': client_status["processed_messages"] + server_status["processed_messages"]
    })

@app.route('/status')
def status():
    """Estado detallado"""
    client_status = get_client_status()
    server_status = get_server_status()
    
    return jsonify({
        'client': client_status,
        'server': server_status,
        'rabbit': {
            'host': os.environ.get('CLOUDAMQP_URL', 'URL no disponible'),
            'queue': RPC_QUEUE
        }
    })

@app.route('/restart', methods=['POST'])
def restart_services():
    """Reiniciar servicios"""
    try:
        init_client()
        init_server()
        return jsonify({"status": "success", "message": "Servicios reiniciados"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/ping')
def ping():
    """Endpoint simple para mantener la aplicación activa"""
    return "pong"
