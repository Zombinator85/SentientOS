import os
from telegram_bridge import TelegramBridge

bridge = TelegramBridge(
    model_slug=os.getenv("GPT4_MODEL", "openai/gpt-4o"),
    bot_token=os.getenv("BOT_TOKEN_GPT4O"),
    port=9977,
)
app = bridge.app

if __name__ == "__main__":
    bridge.run()
