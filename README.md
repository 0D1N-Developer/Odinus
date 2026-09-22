# Odinus

Odinus is a Discord bot written in Python. Its first command, `/publicar`, posts a
message in the channel where it is invoked.

## Requirements

- Python 3.10 or later
- A Discord application with a bot created in the
  [Discord Developer Portal](https://discord.com/developers/applications)

## Setup

1. Create and activate a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. Install dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

3. Create your local configuration from the public template:

   ```powershell
   Copy-Item .env.example .env
   ```

4. Open `.env` and set `DISCORD_TOKEN` to the bot token obtained from the Discord
   Developer Portal. Do not share this value.

5. Install the bot in your server using an installation URL with the `bot` and
   `applications.commands` scopes.

6. Start Odinus:

   ```powershell
   py main.py
   ```

## Usage

In a channel where the bot can send messages, run:

```
/publicar mensaje: Hello from Odinus
```

The bot posts the supplied text in that channel and sends a private confirmation.

## Security

`.env` is local-only and must never be committed or uploaded. It is excluded by
`.gitignore`; only `.env.example`, which contains no credentials, belongs in the
repository. If a credential is ever exposed, revoke and replace it immediately.
