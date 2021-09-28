import ccxt
import logging
import random
from dataclasses import dataclass, InitVar
from datetime import datetime, timedelta
from typing import Optional
from retry import retry
from ccxt import NetworkError, AuthenticationError

from btclab.telegram import TelegramBot
from btclab.common import Strategy

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

    def time_since_last_order(self, symbol: str, strategy: Strategy, is_dummy: bool) -> Optional[timedelta]:
        from btclab import database
        """
        Returns the time passed since the last order was placed for 
        given symbol and strategy or None if no orders have been placed
        """
        last_order = database.get_latest_order(self.user_id, symbol, is_dummy, strategy)
        if last_order is None:
            return None
        
        diff = datetime.utcnow() - last_order.datetime_.replace(tzinfo=None)
        assert diff.seconds >= 0, \
                f'Last order for {symbol} (id {last_order.id}) has a date in the future {last_order.datetime_}'
        
        return diff

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
        greeting = f'{formal} {name}' if random.randrange(2) else f'{casual} {name}!'
        return greeting

    def contacted_in_the_last(self, hours: int) -> bool:
        if self.last_contact is None:
            return False
        
        duration = datetime.now() - self.last_contact
        duration_in_hours = divmod(duration.total_seconds(), 3600)[0]
        return duration_in_hours < hours

    def get_dca_summary(self) -> str:
        from btclab import database

        msg = 'Next periodic purchases:'
        if len(self.dca_config) == 0:
            msg = 'You don\'t have any periodic purchase configured'
        else:
            for symbol, config in self.dca_config.items():
                last_dca_order = database.get_latest_order(self.user_id, symbol, config['is_dummy'], Strategy.DCA)
                days_since_last_purchase = (datetime.now() - last_dca_order.datetime_).days
                days_remaining = config['frequency'] - days_since_last_purchase
                base_ccy = symbol.split('/')[0]
                quote_ccy = symbol.split('/')[1]

                if days_remaining > 0:
                    if days_remaining == 1:
                        msg += f'\n - {config["order_cost"]:g} {quote_ccy} of {base_ccy} tomorrow' 
                    elif days_remaining > 1:
                        msg += f'\n - {config["order_cost"]:g} {quote_ccy} of {base_ccy} in {str(days_remaining)} days'
        return msg

    def get_symbols(self) -> set[str]:
        d1 = set(self.dca_config.keys())
        d2 = set(self.dips_config.keys())
        return d1.union(d2)

    def get_base_currency_balances(self) -> Optional[str]:
        if not self.exchange.has['fetchTickers']:
            logger.warning(f'{self.exchange.name} exchange does not support fetchTickers method')
            return None
        
        symbols = self.get_symbols()
        msg = '\nCurrent prices for your symbols are:\n'
        tickers = self.exchange.fetch_tickers(symbols)
        for item in tickers.values():
            msg += f' - {item["symbol"]}: {item["last"]:,.8g} ({item["percentage"]:.1f}%)\n'
        return msg

    @retry(NetworkError, delay=15, jitter=5, logger=logger)
    def get_quote_currency_balances(self) -> str:
        all_symbols = self.get_symbols()
        quote_currencies = set([symbol.split('/')[1] for symbol in all_symbols])
        msg = f'\nAvailable balance:'
        for quote_ccy in quote_currencies:
            try:
                balance = self.exchange.fetch_balance()[quote_ccy]['free']
            except AuthenticationError as ae:
                user = self.first_name + ' ' + self.last_name
                logger.error(f'Unable to authenticate user {user}. Check API permissions')
                logger.error(ae)
                return 'User not authenticated'

            msg += f'\n - {quote_ccy}: {balance:,.2f}'
        return msg

    def get_summary(self) -> Optional[str]:
        current_hour = datetime.now().hour
        if current_hour in (8, 9, 10, 21, 22, 23) and not self.contacted_in_the_last(hours=6) and self.notify_to_telegram:
            msg = self._greet()
            msg += '\n' + self.get_base_currency_balances()
            msg += '\n' + self.get_dca_summary()           
            msg += '\n' + self.get_quote_currency_balances()
            return msg
        return None
            
            

