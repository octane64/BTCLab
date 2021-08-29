import ccxt
from dataclasses import dataclass, InitVar
from datetime import datetime
from typing import Optional

from btclab.telegram import TelegramBot


@dataclass
class Account():
    user_id: str
    first_name: str
    last_name: str
    email: str
    created_on: datetime
    
    telegram_bot: Optional[TelegramBot]
    dca_config: dict
    dips_config: dict
    notify_to_telegram: bool
    notify_to_email: bool

    def __post_init__(self, api_key, api_secret):
        self.exchange = ccxt.binance( # TODO Change to dynamically create instance of exchange from its id
            {
                'apiKey': api_key, 
                'secret': api_secret, 
                'enableRateLimit': True 
            }
        )