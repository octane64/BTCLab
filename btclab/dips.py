from ccxt import Exchange
from dataclasses import dataclass
from datetime import datetime

from btclab.logconf import logger
from btclab import database
from btclab import crypto
from btclab.common import Strategy
from btclab.users import Account


@dataclass
class DipsManager():
    user_account: Account

    @staticmethod
    def bought_within_the_last(hours: float, symbol:str, orders: dict) -> bool:
        """
        Returns true if symbol was bought within the last hours, false otherwise
        """
        if symbol not in orders:
            return False    
        
        now = datetime.now()
        timestamp = orders[symbol]['timestamp'] / 1000
        bought_on = datetime.fromtimestamp(timestamp)
        diff = now - bought_on
        return diff.days <= hours

    def _buy_initial_drop(self, ticker, dip_config: dict, symbols_stats: dict, dry_run: bool):
        """
        Places a new buy order if at current price the change in the last 24h represents a drop
        that surpasses the min_drop limit and the symbol has not been bought in the last 24 hours
        """
        user_id = self.user_account.user_id
        symbol = ticker['symbol']
        cost = dip_config['order_cost']
        if dip_config['min_drop_units'] == 'SD':
            min_drop = dip_config['min_drop_value'] * symbols_stats[symbol]['std_dev'] * -100
        else:
            min_drop = dip_config['min_drop_value'] * -1
        
        days_from_last_order = database.days_from_last_order(user_id, symbol, Strategy.BUY_THE_DIPS, dip_config['is_dummy'])
        
        
        if days_from_last_order == 0:
            logger.debug(f'{symbol}: Today\'s order already placed!')
            return

        if not ticker['percentage'] < min_drop:
            msg = f'{symbol}: Last 24h change is {ticker["percentage"]:+.2f}%, min drop of {min_drop:.2f}% not met'
            logger.debug(msg)
            return

        if ticker['percentage'] < min_drop and days_from_last_order > 0:
            asset = symbol.split('/')[0]
            quote_ccy = symbol.split('/')[1]
            price = ticker['last']
            is_dummy = dip_config['is_dummy'] or dry_run
            order = crypto.place_buy_order(exchange=self.user_account.exchange, 
                                            symbol=symbol, 
                                            price=price,
                                            order_cost=cost, 
                                            order_type='market', 
                                            is_dummy=is_dummy,
                                            dry_run=dry_run)
            msg = (f'Buying {order["cost"]:,.2g} {quote_ccy} of {asset} @ {price:,.6g}. '
                    f'Drop in last 24h is {ticker["percentage"]:+.2f}%')
            
            if is_dummy:
                msg += '. (Running in simulation mode, balance was not affected)'
            
            logger.debug(msg)
            if self.user_account.notify_to_telegram:
                self.telegram_bot.send_msg(msg)
            return order
        
        return None

    def _buy_additional_drop(self, ticker, dip_config: dict, dry_run: bool):
        """
        Places a new buy order if symbol has been bought recently and last 24h drop 
        surpasses the min_next_drop limit
        """
        user_id = self.user_account.user_id
        exchange = self.user_account.exchange
        symbol = ticker['symbol']
        last_order = database.get_latest_order(user_id, symbol, dip_config['is_dummy'], Strategy.BUY_THE_DIPS)
        if last_order is None:
            return None
        
        drop_from_last_order = (ticker['ask'] / last_order['price'] - 1) * 100
        if drop_from_last_order < dip_config['min_additional_drop']:
            asset = symbol.split('/')[0]
            quote_ccy = symbol.split('/')[1]
            price = ticker['ask']
            cost = last_order['cost'] + dip_config['increase_cost_by']
            is_dummy = dip_config['is_dummy'] or dry_run
            order = crypto.place_buy_order(exchange, symbol, price, cost, 'market', is_dummy)
            msg = (f'Buying {order["cost"]:,.2f} {quote_ccy} of {asset} @ {price:,.2f}. '
                    f'Current price is {drop_from_last_order:.2f}% from the previous buy order')
            
            if is_dummy:
                msg += '. (Running in simulation mode, balance was not affected)'
            
            logger.debug(msg)
            if self.user_account.notify_to_telegram:
                self.telegram_bot.send_msg(msg)
            return order
        return None

    def buydips(self, symbols_stats: dict, dry_run: bool):
        """
        Place orders for buying dips
        """
        user_id = self.user_account.user_id
        exchange = self.user_account.exchange
        for symbol, dip_config in self.user_account.dips_config.items():
            ticker = exchange.fetch_ticker(symbol)
            order = self._buy_initial_drop(ticker, dip_config, symbols_stats, dry_run)
            
            if order is None:
                order = self._buy_additional_drop(ticker, dip_config, dry_run)
            
            if order is not None:
                database.save_order(order, user_id, Strategy.BUY_THE_DIPS)
