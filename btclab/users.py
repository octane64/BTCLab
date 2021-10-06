import ccxt
import logging
import random
from dataclasses import dataclass, InitVar
from datetime import datetime, timedelta
from typing import Optional
from retry import retry
from ccxt import NetworkError, AuthenticationError

from telegram import TelegramBot
import dca
from common import Strategy

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
        """
        Returns the time passed since the last order was placed for 
        given symbol and strategy or None if no orders have been placed
        """
        from btclab import database
        last_order = database.get_latest_order(self.user_id, symbol, is_dummy, strategy)
        if last_order is None:
            return None
        
        diff = datetime.utcnow() - last_order.datetime_.replace(tzinfo=None)
        assert diff.total_seconds() >= 0, \
                f'Last order for {symbol} (id {last_order.id}) has a date in the future {last_order.datetime_}'
        
        return diff

    def _greet(self) -> str:
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
        
        duration = datetime.utcnow() - self.last_contact
        duration_in_hours = divmod(duration.total_seconds(), 3600)[0]
        return duration_in_hours < hours

    def get_symbols(self) -> set[str]:
        d1 = set(self.dca_config.keys())
        d2 = set(self.dips_config.keys())
        return d1.union(d2)

    @retry(NetworkError, delay=15, jitter=5, logger=logger)
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

    def get_summary(self, dry_run: str) -> Optional[str]:
        current_hour = datetime.now().hour
        if current_hour in (7, 8, 22, 23) and not self.contacted_in_the_last(hours=6) and self.notify_to_telegram:
            msg = self._greet()
            msg += '\n' + self.get_base_currency_balances()
            msg += '\n' + dca.get_dca_summary(self, dry_run)
            msg += '\n' + self.get_quote_currency_balances()
            return msg
        return None
            
            

