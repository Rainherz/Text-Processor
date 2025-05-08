/**
 * TextPro RPC - Cliente de Procesamiento de Texto
 * JavaScript principal para la aplicación web
 */

// Manejar el cambio de tema (Oscuro/Claro)
document.addEventListener('DOMContentLoaded', () => {
    // Comprobar preferencia guardada
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme) {
        document.documentElement.setAttribute('data-bs-theme', savedTheme);
        updateThemeIcon(savedTheme);
    } else if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
        // Usar preferencia del sistema
        document.documentElement.setAttribute('data-bs-theme', 'dark');
        updateThemeIcon('dark');
    }
    
    // Escuchar cambios en el botón de tema
    const themeToggle = document.getElementById('theme-toggle');
    if (themeToggle) {
        themeToggle.addEventListener('click', toggleTheme);
    }
    
    // Verificar estado del servidor al cargar
    checkServerStatus();
    
    // Verificar estado del servidor cada 30 segundos
    setInterval(checkServerStatus, 30000);
    
    // Añadir efectos de hover y focus a tarjetas
    addCardInteractivity();
});

/**
 * Alternar entre temas claro y oscuro
 */
function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-bs-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    
    // Animar la transición
    document.body.style.opacity = '0.9';
    
    setTimeout(() => {
        document.documentElement.setAttribute('data-bs-theme', newTheme);
        localStorage.setItem('theme', newTheme);
        updateThemeIcon(newTheme);
        document.body.style.opacity = '1';
    }, 200);
}

/**
 * Actualizar el icono del botón de tema
 * @param {string} theme - 'dark' o 'light'
 */
function updateThemeIcon(theme) {
    const themeToggle = document.getElementById('theme-toggle');
    if (themeToggle) {
        themeToggle.innerHTML = theme === 'dark' 
            ? '<i class="bi bi-sun"></i>' 
            : '<i class="bi bi-moon-stars"></i>';
    }
}

/**
 * Verificar el estado del servidor RPC
 */
function checkServerStatus() {
    console.log("Verificando estado del servidor...");
    
    // Usar /health primero, si falla usar /ping como respaldo
    fetch('/health')
        .then(response => response.json())
        .then(data => {
            console.log("Respuesta de /health:", data);
            
            // Determinar el estado de conexión basado en diferentes formatos posibles
            let isConnected = false;
            
            // Formato 1: { client_connected: true, server_running: true }
            if (data.client_connected !== undefined && data.server_running !== undefined) {
                isConnected = data.client_connected && data.server_running;
            }
            // Formato 2: { rpc_connected: true }
            else if (data.rpc_connected !== undefined) {
                isConnected = data.rpc_connected;
            }
            // Formato 3: { services: { client: "ok", server: "ok" } }
            else if (data.services) {
                isConnected = data.services.client === "ok" && data.services.server === "ok";
            }
            // Formato 4: { app: "ok" } - En este caso no tenemos información suficiente
            else if (data.app === "ok") {
                // Intentar obtener más información con /status
                fetch('/status')
                    .then(response => response.json())
                    .then(statusData => {
                        console.log("Respuesta de /status:", statusData);
                        if (statusData.client && statusData.server) {
                            updateConnectionStatus(
                                statusData.client.connected && 
                                statusData.server.running
                            );
                        } else {
                            // No tenemos suficiente información, asumir conectado si la app está bien
                            updateConnectionStatus(true);
                        }
                    })
                    .catch(error => {
                        console.error('Error verificando estado detallado:', error);
                        // Asumir conectado si /health dice que la app está bien
                        updateConnectionStatus(true);
                    });
                return;
            }
            
            updateConnectionStatus(isConnected);
        })
        .catch(error => {
            console.error('Error verificando estado en /health:', error);
            
            // Intenta con /ping como alternativa
            fetch('/ping')
                .then(response => response.json())
                .then(data => {
                    console.log("Respuesta de /ping:", data);
                    
                    let isConnected = false;
                    
                    if (data.rpc_connected !== undefined) {
                        isConnected = data.rpc_connected;
                    } else if (data.services) {
                        isConnected = data.services.client === "ok" && data.services.server === "ok";
                    } else if (data.status === "ok") {
                        // Si solo sabemos que el servidor está OK, asumimos que está conectado
                        isConnected = true;
                    }
                    
                    updateConnectionStatus(isConnected);
                })
                .catch(error => {
                    console.error('Error verificando estado en /ping:', error);
                    updateConnectionStatus(false);
                });
        });
}

/**
 * Actualizar indicadores de estado de conexión
 * @param {boolean} connected - Estado de conexión 
 */
function updateConnectionStatus(connected) {
    console.log("Estado de conexión:", connected ? "Conectado" : "Desconectado");
    
    const indicator = document.querySelector('.status-indicator');
    const statusText = document.querySelector('.status-indicator + div p');
    const processBtn = document.getElementById('process-btn');
    
    if (indicator && statusText) {
        if (connected) {
            indicator.className = 'status-indicator me-3 connected';
            indicator.innerHTML = '<i class="bi bi-cloud-check"></i>';
            statusText.textContent = 'Conectado y funcionando';
            if (processBtn) processBtn.disabled = false;
            
            // Quitar alerta de advertencia si existe
            const warningMsg = document.querySelector('#text-form .alert-warning');
            if (warningMsg) {
                warningMsg.remove();
            }
        } else {
            indicator.className = 'status-indicator me-3 disconnected';
            indicator.innerHTML = '<i class="bi bi-cloud-slash"></i>';
            statusText.textContent = 'Desconectado';
            if (processBtn) processBtn.disabled = true;
            
            // Mostrar alerta si no existe
            updateUIBasedOnConnection(false);
        }
    } else {
        console.warn("No se encontraron los elementos de indicador de estado");
    }
}

/**
 * Añadir interactividad a las tarjetas
 */
function addCardInteractivity() {
    const cards = document.querySelectorAll('.card');
    
    cards.forEach(card => {
        card.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-5px)';
        });
        
        card.addEventListener('mouseleave', function() {
            this.style.transform = 'translateY(0)';
        });
        
        card.addEventListener('focus', function() {
            this.style.transform = 'translateY(-5px)';
        });
        
        card.addEventListener('blur', function() {
            this.style.transform = 'translateY(0)';
        });
    });
}

/**
 * Actualizar UI basado en estado de conexión
 * @param {boolean} connected - Estado de conexión
 */
function updateUIBasedOnConnection(connected = null) {
    // Si no se proporciona un valor, intentar determinarlo
    if (connected === null) {
        connected = document.querySelector('.status-indicator.connected') !== null;
    }
    
    const processBtn = document.getElementById('process-btn');
    
    if (processBtn) {
        processBtn.disabled = !connected;
    }
    
    const form = document.getElementById('text-form');
    const existingWarning = document.querySelector('#text-form .alert-warning');
    
    if (!connected && form && !existingWarning) {
        const warningMsg = document.createElement('div');
        warningMsg.className = 'alert alert-warning';
        warningMsg.innerHTML = '<i class="bi bi-exclamation-triangle"></i> Servidor RPC no disponible. Por favor verifica la conexión. <button id="reconnect-btn" class="btn btn-sm btn-warning ms-2">Reconectar</button>';
        
        form.prepend(warningMsg);
        
        // Añadir evento al botón de reconexión
        document.getElementById('reconnect-btn').addEventListener('click', function() {
            this.disabled = true;
            this.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Reconectando...';
            
            fetch('/restart', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            })
            .then(response => response.json())
            .then(data => {
                this.innerHTML = 'Reconectar';
                this.disabled = false;
                
                if (data.status === 'success') {
                    // Esperar un momento y verificar el estado
                    setTimeout(checkServerStatus, 2000);
                } else {
                    console.error('Error al reconectar:', data.message);
                    alert('Error al reconectar: ' + data.message);
                }
            })
            .catch(error => {
                console.error('Error:', error);
                this.innerHTML = 'Reconectar';
                this.disabled = false;
                alert('Error al reconectar: ' + error);
            });
        });
    } else if (connected && existingWarning) {
        existingWarning.remove();
    }
}

/**
 * Mostrar el resultado de una operación
 * @param {string} operation - Nombre de la operación
 * @param {string} result - Resultado de la operación
 */
function showResult(operation, result) {
    const resultOperation = document.getElementById('result-operation');
    const resultContent = document.getElementById('result-content');
    
    if (resultOperation && resultContent) {
        resultOperation.textContent = operation;
        resultContent.textContent = result;
        
        // Ocultar formulario y mostrar resultado
        document.querySelector('.main-card').style.display = 'none';
        
        const resultCard = document.querySelector('.result-card');
        resultCard.style.display = 'block';
        resultCard.style.animation = 'fadeIn 0.5s ease';
    }
}

/**
 * Copiar texto al portapapeles
 * @param {string} text - Texto a copiar
 * @param {HTMLElement} button - Botón que se presionó
 */
function copyToClipboard(text, button) {
    navigator.clipboard.writeText(text)
        .then(() => {
            const originalHTML = button.innerHTML;
            button.innerHTML = '<i class="bi bi-check"></i> Copiado';
            
            setTimeout(() => {
                button.innerHTML = originalHTML;
            }, 2000);
        })
        .catch(err => {
            console.error('Error al copiar: ', err);
            alert('No se pudo copiar el texto');
        });
}

/**
 * Animar elementos cuando aparecen en el viewport
 */
function animateOnScroll() {
    const elementsToAnimate = document.querySelectorAll('.animate-on-scroll');
    
    if (elementsToAnimate.length === 0) return;
    
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.2 });
    
    elementsToAnimate.forEach(element => {
        observer.observe(element);
    });
}

// Inicializar animaciones si hay elementos para animar
if (document.querySelector('.animate-on-scroll')) {
    animateOnScroll();
    window.addEventListener('scroll', animateOnScroll);
}
