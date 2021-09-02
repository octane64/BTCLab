import ccxt
from dataclasses import dataclass, InitVar
from datetime import datetime
from typing import Optional
import pickle

from btclab.telegram import TelegramBot
from btclab import crypto


@dataclass
class Account():
    user_id: str
    first_name: str
    last_name: str
    email: str
    created_on: datetime
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
        if datetime.now().hour < 12:
            time = 'morning'
        elif hour <= 18:
            time = 'afternoon'
        else:
            time = 'evening'
        return f'Good {time} {self.first_name}'

    def _set_as_greeted(self):
        try:
            with open('greetings.pkl', 'rb') as f:
                greetings = pickle.load(f)
        except FileNotFoundError:
            greetings = {}
        
        greetings[self.user_id] =  datetime.now()
        
        with open('greetings.pkl', 'wb') as f:
            pickle.dump(greetings, f)

    def already_greeted_today(self) -> bool:
        try:
            with open('greetings.pkl', 'rb') as f:
                greetings = pickle.load(f)
        except FileNotFoundError:
            return False

        if self.user_id not in greetings:
            return False

        last_time = greetings[self.user_id]
        time_since_last_greeting = datetime.now() - last_time
        return time_since_last_greeting.days <= 1

    def greet_with_symbols_summary(self):
        if datetime.now().hour >= 7 and not self.already_greeted_today():
            d1 = set(self.dca_config.keys())
            d2 = set(self.dips_config.keys())
            all_symbols = d1.union(d2)
            msg = self._greet() + '\n\n' + crypto.get_symbols_summary(all_symbols, self.exchange)
            
            if self.notify_to_telegram:
                self.telegram_bot.send_msg(msg)
            self._set_as_greeted()