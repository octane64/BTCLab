import ccxt
import logging
import random
from dataclasses import dataclass, InitVar
from datetime import datetime
from typing import Optional
from retry import retry
from ccxt import NetworkError

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
        formal = 'Good ' + time
        casual = 'What\'s up'
        tmp = formal if random.randrange(2) else casual
        return f'{tmp} {name}'

    def contacted_in_the_last(self, hours: int) -> bool:
        if self.last_contact is None:
            return False
        
        duration = datetime.now() - self.last_contact
        duration_in_hours = divmod(duration.total_seconds(), 3600)[0]
        return duration_in_hours < hours

    def get_dca_summary(self) -> str:
        msg = 'Your next periodic purchases:'
        if len(self.dca_config) == 0:
            msg = 'You don\'t have any periodic purchase configured'
        else:
            for symbol, config in self.dca_config.items():
                if config['days_to_buy_again'] > 0:
                    if config['days_to_buy_again'] == 1:
                        days_remaining = 'tomorrow'
                    elif config['days_to_buy_again'] > 1:
                        days_remaining = f'in {str(config["days_to_buy_again"])} days'
                msg += f'\n - {symbol} {days_remaining}' 
        
        return msg

    @retry(NetworkError, delay=15, jitter=5, logger=logger)
    def greet_with_symbols_summary(self):
        from btclab import database
        current_hour = datetime.now().hour
        if current_hour in (7, 8, 21, 22) and not self.contacted_in_the_last(hours=6):
            d1 = set(self.dca_config.keys())
            d2 = set(self.dips_config.keys())
            all_symbols = d1.union(d2)
            msg = self._greet() + '. ' + crypto.get_symbols_summary(all_symbols, self.exchange)
            msg += '\n' + self.get_dca_summary()
            msg += f'\n\nAvaiable balance:'
            
            quote_currencies = set([symbol.split('/')[1] for symbol in all_symbols])
            for quote_ccy in quote_currencies:
                balance = self.exchange.fetch_balance()[quote_ccy]['free']
                msg += f'\n - {quote_ccy}: {balance:,.2f}'

            if self.notify_to_telegram:
                self.telegram_bot.send_msg(msg)
                database.update_last_contact(self.user_id)
            

