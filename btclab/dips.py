from common import Strategy
import crypto
import db
from telegram import TelegramBot
from dataclasses import dataclass
from datetime import datetime
from logconf import logger
from ccxt import Exchange


@dataclass
class DipsManager():
    dips_config: dict

    @staticmethod
    def bought_within_the_last(hours: float, symbol:str, orders: dict) -> bool:
        """
        Returns true if symbol was bought within the last hours, false otherwise
        """
        if symbol not in orders:
            return False    
        
        now = datetime.now()
        timestamp = orders[symbol]['timestamp'] # / 1000
        bought_on = datetime.fromtimestamp(timestamp)
        diff = now - bought_on
        return diff.days <= hours

    def _buy_initial_drop(self, user_id: str, exchange: Exchange, ticker, dip_config: dict, 
                            symbols_stats: dict, telegram_bot: TelegramBot, dry_run: bool):
        """
        Places a new buy order if at current price the change in the last 24h represents a drop
        that surpasses the min_drop limit and the symbol has not been bought in the last 24 hours
        """
        symbol = ticker['symbol']
        cost = self.dips_config[symbol]['order_cost']
        if dip_config['min_drop_units'] == 'SD':
            min_drop = dip_config['min_drop_value'] * symbols_stats[symbol]['std_dev'] * -100
        else:
            min_drop = dip_config['min_drop_value'] * -1
        
        if ticker['percentage'] < min_drop and db.days_from_last_order(user_id, symbol, Strategy.BUY_THE_DIPS) > 0:
            asset = symbol.split('/')[0]
            quote_ccy = symbol.split('/')[1]
            price = ticker['last']
            order = crypto.place_buy_order(exchange, symbol, price, cost, 'market', dry_run)
            msg = (f'Buying {order["cost"]:,.2g} {quote_ccy} of {asset} @ {price:,.6g}. '
                    f'Drop in last 24h is {ticker["percentage"]:.2f}%')
            
            if dry_run:
                msg += '. (Running in simulation mode, balance was not affected)'
            
            logger.debug(msg)
            telegram_bot.send_msg(msg)
            return order
        
        return None

    def _buy_additional_drop(self, user_id: str, exchange: Exchange, ticker, dip_config: dict, 
                                telegram_bot: TelegramBot, dry_run: bool):
        """
        Places a new buy order if symbol has been bought recently and last 24h drop 
        surpasses the min_next_drop limit
        """
        symbol = ticker['symbol']
        last_order = db.get_latest_order(user_id, Strategy.BUY_THE_DIPS)
        if last_order is None:
            return None
        
        drop_from_last_order = (ticker['ask'] / last_order['price'] - 1) * 100
        if drop_from_last_order < dip_config['min_additional_drop']:
            asset = symbol.split('/')[0]
            quote_ccy = symbol.split('/')[1]
            price = ticker['ask']
            cost = last_order['cost'] + dip_config['increase_cost_by']
            order = crypto.place_buy_order(exchange, symbol, price, cost, 'market', dry_run)
            msg = (f'Buying {order["cost"]:,.2f} {quote_ccy} of {asset} @ {price:,.2f}. '
                    f'Current price is {drop_from_last_order:.2f}% from the previous buy order')
            
            if self.dry_run:
                msg += '. (Running in simulation mode, balance was not affected)'
            
            logger.debug(msg)
            telegram_bot.send_msg(msg)
            return order
        return None

    def buydips(self, user_id:str, exchange: Exchange, symbols_stats: dict, telegram_bot: TelegramBot, dry_run: bool):
        """
        Place orders for buying dips
        """
        for symbol, dip_config in self.dips_config.items():
            ticker = exchange.fetch_ticker(symbol)
            order = self._buy_initial_drop(user_id, exchange, ticker, dip_config, symbols_stats, telegram_bot, dry_run)
            
            if order is None:
                order = self._buy_additional_drop(user_id, exchange, ticker, dip_config, telegram_bot, dry_run)
            
            if order is not None:
                db.save_order(order, user_id, Strategy.BUY_THE_DIPS, dry_run)
