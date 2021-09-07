import ccxt
import logging
from dataclasses import dataclass, InitVar
from datetime import datetime, date
from typing import Optional

from btclab.telegram import TelegramBot
from btclab import crypto


logger = logging.getLogger(__name__)

@dataclass
class Account():
    user_id: int
    first_name: str
    last_name: str
    email: str
    created_on: datetime
    last_contact: datetime
    exchange_id: str
    api_key: InitVar[str]
    api_secret: InitVar[str]
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

    def _greet(self):
        hour = datetime.now().hour
        name = self.first_name.split(' ')[0]
        if datetime.now().hour < 12:
            time = 'morning'
        elif hour <= 18:
            time = 'afternoon'
        else:
            time = 'evening'
        return f'Good {time} {name}'

    def contacted_today(self) -> bool:
        if self.last_contact is None:
            return False
        
        if date.today() == self.last_contact.date():
            return True
        return False

    def greet_with_symbols_summary(self) -> bool:
        current_hour = datetime.now().hour
        if current_hour in (7, 22) and not self.contacted_today():
            d1 = set(self.dca_config.keys())
            d2 = set(self.dips_config.keys())
            all_symbols = d1.union(d2)
            msg = self._greet() + '. ' + crypto.get_symbols_summary(all_symbols, self.exchange)
            

            if self.notify_to_telegram:
                self.telegram_bot.send_msg(msg)
            
            return True
        return False