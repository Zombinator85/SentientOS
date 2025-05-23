import os
from telegram_bridge import TelegramBridge

bridge = TelegramBridge(
    model_slug=os.getenv("MIXTRAL_MODEL", "mixtral"),
    bot_token=os.getenv("BOT_TOKEN_MIXTRAL"),
    port=9988,
)
app = bridge.app

if __name__ == "__main__":
    bridge.run()
