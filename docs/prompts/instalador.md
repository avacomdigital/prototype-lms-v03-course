## Requerimiento 

Debes realizar una versión instalable en en una carpeta de "/dist" para distribuir el software, está pensado principalmente para Windows.

## Constitución

1. No debes modificar el comportamiento funcional existente de AVACOM OPS Master.
2. El instalador únicamente debe resolver distribución, instalación, configuración inicial, ejecución y desinstalación.
3. Debes considerar que en el mismo nodo/host donde se instala AVACOM OPS Master también podrá encontrarse instalado AVACOM Biblioteca.
4. Ambos productos deben poder coexistir sin sobrescribir:
    - archivos;
    - configuraciones;
    - servicios;
    - bases de datos;
    - procesos;
    - logs;
    - puertos;
    - accesos directos.
5. La API de AVACOM OPS Master se encuentra actualmente en: ./backend
6. La API AVACOM OPS BACKEND debe poder ejecutarse por defecto escuchando en: 0.0.0.0:8000
7. Se permiten internamente scripts .bat, PowerShell, ejecutables auxiliares o comandos del sistema, pero estos no deben requerir interacción manual del usuario.
8. Los scripts .bat, powershell, ejecutables auxiliares o comandos deben ser ejecutados por el instalador wizard
9. No modifiques la arquitectura del software AVACOM OPS Master, ni del backend
10. Si el backend requeire variables .env debes generarlas a través de los comandos
11. No utilizar python manage.py runserver como mecanismo definitivo de ejecución del backend si existe una alternativa compatible con el comportamiento actual. Para Windows se puede utilizar un servidor WSGI como Waitress, manteniendo: 0.0.0.0:8000


## Especificación

El AVACOM OPS Master tiene tanto la aplicación backend, cómo la aplicación frontend llamada AVACOM OPS Master, debe instalar lo suficiente para correr el backend en Django Rest Framework y la aplicación de AVACOM OPS Master. 

Debes considerar que pueden existir comandos de winget, bat, pero no puede ser una instalación que requiera escribir comandos, debe ser al estilo wizard.

1. Componentes a instalar

El paquete de distribución debe contener como mínimo:

AVACOM OPS Master
│
├── Frontend
│   └── Aplicación .NET C# MAUI para Windows
│
├── Backend
│   ├── Django
│   ├── Django REST Framework
│   ├── dependencias Python
│   └── configuración requerida
│
├── Runtime
│   └── dependencias necesarias para ejecutar el backend
│
├── Config
│   └── configuración local del nodo
│
├── Logs
│
└── Uninstaller

El usuario no deberá conocer esta estructura para utilizar el producto.

2. Experiencia del Install Wizard

El instalador debe presentar un flujo gráfico similar a:

Bienvenido
   ↓
License / Información AVACOM LMS 2.0
   ↓
Installation Directory
   ↓
System Validation
   ↓
Ready to Install
   ↓
Installing
   ↓
Backend Configuration
   ↓
Installation Completed
Pantalla 1 — Welcome

Pantalla 2 — Información

Mostrar:

AVACOM OPS Master

This wizard will install AVACOM OPS Master
and its required local services on this computer.

No exponer detalles técnicos innecesarios al usuario.

Pantalla 3 — Ruta de instalación

Ruta sugerida:

C:\Program Files\AVACOM\OPS Master\

AVACOM Biblioteca deberá utilizar una ruta independiente, por ejemplo:

C:\Program Files\AVACOM\Biblioteca\

Nunca compartir carpetas de aplicación entre ambos productos.

Pantalla 4 — Validaciones

Antes de instalar, comprobar automáticamente:

Windows 10 / Windows 11
arquitectura compatible
espacio disponible
permisos necesarios
puerto 8000
instalación previa de OPS Master
procesos activos
dependencias críticas

Si el puerto 8000 está ocupado, el instalador deberá:

identificar que existe un conflicto;
no finalizar silenciosamente;
mostrar un mensaje comprensible;
evitar detener procesos externos sin autorización.

Ejemplo:

Port 8000 is currently being used by another application.

AVACOM OPS Master requires this port for its local API.

Please close the conflicting application and retry.
4. Backend Django

El instalador debe preparar automáticamente el backend ubicado actualmente en:

./backend

El backend instalado debe poder ejecutarse sin requerir que el usuario instale manualmente Python.

La solución preferente es distribuir:

Python Runtime
+
dependencias Python
+
Django
+
Django REST Framework
+
Waitress
+
backend AVACOM

dentro del paquete.

Evitar depender de:

pip install
winget install python

durante una instalación normal.

Esto permite instalar AVACOM OPS Master incluso en una LAN completamente offline.

5. Inicialización del backend

Durante la primera instalación deberán ejecutarse automáticamente, cuando correspondan, operaciones como:

database migrations
database initialization
configuration creation
static preparation
runtime validation

Por ejemplo, conceptualmente:

python manage.py migrate

pero el usuario nunca deberá ejecutar este comando directamente.

6. Ejecución del Backend

Una vez instalado, el backend deberá poder iniciarse automáticamente mediante un proceso controlado.

Arquitectura esperada:

Windows
   │
   ├── AVACOM OPS Master.exe
   │
   └── AVACOM OPS Backend
            │
            └── Waitress
                  │
                  └── Django / DRF
                       │
                       └── 0.0.0.0:8000

Se debe estudiar como mecanismo preferente un Windows Service para el backend.

Nombre sugerido:

AVACOMOPSBackend

Esto permite que la API exista independientemente de que el usuario tenga abierta la interfaz MAUI.

7. Inicio y detención

El instalador deberá configurar los componentes para garantizar:

Inicio backend
→
Validación backend
→
Inicio AVACOM OPS Master

Al reiniciar Windows, debe definirse explícitamente si:

AVACOMOPSBackend

inicia automáticamente.

Recomendación:

Startup Type = Automatic

para que el nodo OPS pueda seguir prestando el servicio LAN incluso antes de abrir la interfaz gráfica.

8. Health Check

Se debe establecer un mecanismo para verificar que el backend quedó operativo.

Preferentemente usar un endpoint existente como:

http://127.0.0.1:8000/

o un endpoint específico:

http://127.0.0.1:8000/health/

Si /health/ no existe actualmente, su incorporación deberá tratarse como una modificación independiente y no introducirse automáticamente si viola la Constitución de no modificar comportamiento.

El instalador deberá comprobar como mínimo que el proceso puede iniciar y escuchar correctamente en el puerto 8000.

9. Firewall

Debido a que Django escuchará mediante:

0.0.0.0:8000

el instalador deberá considerar Windows Defender Firewall.

Si es necesario crear una regla, deberá hacerse automáticamente durante la instalación.

Nombre sugerido:

AVACOM OPS Master Backend

Puerto:

TCP 8000

Preferentemente limitada a redes privadas cuando la arquitectura de AVACOM lo permita.

# Tarea

Realizar el instalador de AVACOM OPS Master junto a su respectivo Backend