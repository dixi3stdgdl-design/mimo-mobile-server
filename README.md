# MiMo Mobile Server

**Backend Python para MiMo Mobile.** Servidor WebSocket + HTTP que conecta la app Android con MiMo Code CLI.

---

## Funcionalidades

- **WebSocket Server** — Comunicación en tiempo real con la app Android
- **HTTP Server** — Health check y API endpoints
- **Chat** — Ejecuta prompts de MiMo Code CLI
- **File Operations** — Leer, escribir, eliminar archivos
- **Remote Desktop** — Captura de pantalla vía PowerShell
- **Mouse/Keyboard Control** — Control remoto del PC
- **ADB Device Management** — Gestión de dispositivos Android
- **Build Progress** — Progreso de construcción de proyectos
- **PIN Authentication** — Seguridad con PIN configurable
- **Heartbeat** — Keepalive cada 30 segundos

---

## Arquitectura

```
┌─────────────────────────────────┐
│    WebSocket Server (8765)      │
│    asyncio.Protocol             │
└───────────┬─────────────────────┘
            │
┌───────────▼─────────────────────┐
│    HTTP Server (8080)           │
│    /health, /api/exec           │
└───────────┬─────────────────────┘
            │
┌───────────▼─────────────────────┐
│    MiMo Code CLI (subprocess)   │
└─────────────────────────────────┘
```

---

## Stack Técnico

| Componente | Tecnología |
|------------|------------|
| Lenguaje | Python 3.10+ |
| WebSocket | asyncio.Protocol (custom) |
| HTTP | http.server (stdlib) |
| Dependencias | CERO (solo stdlib) |

---

## Instalación

### Rápida
```bash
chmod +x install.sh
./install.sh
```

### Manual
```bash
# Crear entorno virtual
python3 -m venv venv
source venv/bin/activate

# Configurar
cp .env.example .env
# Editar .env con tu configuración

# Ejecutar
python3 server.py
```

---

## Configuración

Variables de entorno (`.env`):

```bash
MIMO_CMD=~/.mimocode/bin/mimo    # Ruta al CLI
MIMO_AUTH_PIN=MIMO2026           # PIN de autenticación
MIMO_WORKSPACE=~                 # Directorio de trabajo
MIMO_SERVER_NAME=$(hostname)     # Nombre del servidor
MIMO_WS_PORT=8765                # Puerto WebSocket
MIMO_HTTP_PORT=8080              # Puerto HTTP
```

---

## Endpoints

### WebSocket (8765)
- `chat` — Enviar prompt a MiMo Code
- `execute` — Ejecutar comando shell
- `read_file` — Leer archivo
- `write_file` — Escribir archivo
- `list_dir` — Listar directorio
- `screen_stream` — Capturar pantalla
- `mouse_event` — Control de mouse
- `keyboard_event` — Control de teclado

### HTTP (8080)
- `GET /health` — Estado del servidor
- `GET /api/exec?command=...` — Ejecutar comando

---

## Uso con MiMo Mobile

1. Ejecuta el server en tu PC
2. Abre MiMo Mobile en tu celular
3. Ingresa la IP de tu PC en Settings
4. Conecta con PIN: `MIMO2026`

---

## Licencia

MIT License
