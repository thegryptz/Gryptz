import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN: str = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

DEEPINFRA_API_KEY: str = os.environ["DEEPINFRA_API_KEY"]
DEEPINFRA_MODEL: str = os.getenv("DEEPINFRA_MODEL", "meta-llama/Meta-Llama-3.1-70B-Instruct")
DEEPINFRA_BASE_URL: str = "https://api.deepinfra.com/v1/openai"

SCAN_INTERVAL: int = int(os.getenv("SCAN_INTERVAL", "120"))
MIN_LIQUIDITY_USD: float = float(os.getenv("MIN_LIQUIDITY_USD", "5000"))
MIN_VOLUME_1H_USD: float = float(os.getenv("MIN_VOLUME_1H_USD", "10000"))
MIN_BUY_RATIO: float = float(os.getenv("MIN_BUY_RATIO", "0.55"))
MIN_GRYPTZ_SCORE: int = int(os.getenv("MIN_GRYPTZ_SCORE", "60"))
MAX_DEV_HOLD_PCT: float = float(os.getenv("MAX_DEV_HOLD_PCT", "20.0"))
DEXSCREENER_BASE: str = "https://api.dexscreener.com"
