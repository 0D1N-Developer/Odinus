# Odinus

Primera versión funcional de un bot de Discord en Python. Incluye el slash command
`/publicar`, que publica el mensaje indicado en el canal donde se ejecuta.

## Requisitos

- Python 3.10 o posterior
- Una aplicación y bot creados en el [Discord Developer Portal](https://discord.com/developers/applications)

## Instalación

1. Crea y activa un entorno virtual:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. Instala las dependencias:

   ```powershell
   pip install -r requirements.txt
   ```

3. Abre `.env` y asigna el token del bot:

   ```env
   DISCORD_TOKEN=tu_token_real
   ```

4. En el portal de Discord, genera una URL de instalación con los scopes `bot` y
   `applications.commands`, e instala el bot en tu servidor.

5. Inicia Odinus:

   ```powershell
   py main.py
   ```

## Uso

En un canal donde el bot tenga permiso para enviar mensajes, ejecuta:

```
/publicar mensaje: Hola desde Odinus
```

El bot enviará el texto al canal y te confirmará el resultado de forma privada.

## Estructura

- `odinus/app.py`: ciclo de vida del bot y registro de módulos.
- `odinus/cogs/`: comandos de Discord organizados por capacidad.
- `odinus/integrations/`: punto reservado para futuros proveedores externos; esta versión no integra ninguno.
- `odinus/config.py`: configuración desde variables de entorno.
- `odinus/logging_config.py`: logging de consola y `logs/odinus.log`.
