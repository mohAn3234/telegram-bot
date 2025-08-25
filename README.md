# Telegram Bot - Link Tracking & Moderation

A powerful Telegram bot for managing group sessions, tracking Twitter/X links, and moderating users.

## Features

- Session management with `/start` and `/end`
- Twitter/X link tracking and extraction
- User participation monitoring with `/check` and `/unsafelist`
- Advanced moderation commands (mute, ban, restrict)
- Group permission controls
- Exclude specific users from tracking

## Setup

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Create `.env` file with your bot token and user IDs
4. Run: `python bot.py`

## Environment Variables

- `BOT_TOKEN`: Your Telegram bot token from @BotFather
- `AUTHORIZED_IDS`: Comma-separated admin user IDs
- `EXCLUDED_USER_IDS`: Comma-separated user IDs to exclude from tracking

## Deployment

The bot can be deployed on:
- Railway
- Heroku
- PythonAnywhere
- Any Python hosting platform

## Commands

See the code for full command list including moderation and session management commands.
