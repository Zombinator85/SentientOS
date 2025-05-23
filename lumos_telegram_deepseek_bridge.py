import os
from telegram_bridge import TelegramBridge

bridge = TelegramBridge(
    model_slug=os.getenv("DEEPSEEK_MODEL", "deepseek-ai/deepseek-r1-distill-llama-70b-free"),
    bot_token=os.getenv("BOT_TOKEN_DEEPSEEK"),
    port=9966,
)
app = bridge.app

if __name__ == "__main__":
    bridge.run()
