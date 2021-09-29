import logging
from typing import Optional
from ccxt import Exchange
from ccxt.base.errors import InsufficientFunds
from dataclasses import dataclass
from datetime import datetime
from dateutil import parser

from btclab import database
from btclab import crypto
from btclab.common import Strategy
from btclab.users import Account
from btclab.order import Order


logger = logging.getLogger(__name__)

@dataclass
class DipsManager():
    user_account: Account

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
        
        time_elapsed = self.user_account.time_since_last_order(symbol, Strategy.BUY_THE_DIPS, dip_config['is_dummy'])
        if time_elapsed is not None:
            hours_since_last_order = time_elapsed.seconds / 60 / 60
            if hours_since_last_order <= 24:
                logger.debug(f'{symbol}: Today\'s order already placed!')
                return

        if dip_config['last_check_result'] == 'Insufficient funds':
            last_check = parser.parse(dip_config['last_check_date'])
            time_since_last_check = datetime.now() - last_check
            minutes = (time_since_last_check.seconds // 60) % 60
            if minutes < 30:
                logger.info(f'Waiting {minutes} more minutes to check again for dips in {symbol}')
                return

        if not ticker['percentage'] < min_drop:
            msg = f'{symbol}: Last 24h change is {ticker["percentage"]:+.2f}%, min drop of {min_drop:.2f}% not met'
            logger.info(msg)
            return
        
        asset = symbol.split('/')[0]
        quote_ccy = symbol.split('/')[1]
        price = ticker['last']
        is_dummy = dip_config['is_dummy'] or dry_run
        order = None

        try:
            order = crypto.place_buy_order(exchange=self.user_account.exchange, 
                                            user_id=user_id,
                                            symbol=symbol, 
                                            price=price,
                                            order_cost=cost, 
                                            order_type='market', 
                                            strategy=Strategy.BUY_THE_DIPS,
                                            is_dummy=is_dummy,
                                            dry_run=dry_run)
        except InsufficientFunds:
            database.update_last_check(self.user_account.user_id, symbol, Strategy.BUY_THE_DIPS, 'Insufficient funds')
            logger.info('Insufficient funds')
            quote_ccy = symbol.split('/')[1]
            base_ccy = symbol.split('/')[0]
            msg = f'Insufficient funds to buy {cost:.1f} {quote_ccy} of {base_ccy}. Trying again in 30 minutes'
            self.user_account.telegram_bot.send_msg(msg)
            return None

        if order:
            database.update_last_check(self.user_account.user_id, symbol, Strategy.BUY_THE_DIPS, 'Order placed')
            msg = (f'Buying {order["cost"]:,.2f} {quote_ccy} of {asset} @ {price:,.6g}. '
                    f'Drop in last 24h is {ticker["percentage"]:+.2f}%')
            if is_dummy:
                msg += '. (Running in simulation mode, balance was not affected)'
        else:
            database.update_last_check(self.user_account.user_id, symbol, Strategy.BUY_THE_DIPS, 'No action')
        
        logger.info(msg)
        if self.user_account.notify_to_telegram:
            self.user_account.telegram_bot.send_msg(msg)
        return order
        

    def _buy_additional_drop(self, ticker, dip_config: dict, dry_run: bool) -> Optional[Order]:
        """
        Places a new buy order if symbol has been bought recently and last 24h drop 
        surpasses the min_next_drop limit
        """
        user_id = self.user_account.user_id
        exchange = self.user_account.exchange
        symbol = ticker['symbol']
        is_dummy = dip_config['is_dummy'] or dry_run
        last_order = database.get_latest_order(user_id, symbol, is_dummy, Strategy.BUY_THE_DIPS)
        if last_order is None:
            return None
        
        if dip_config['last_check_result'] == 'Insufficient funds':
            last_check = parser.parse(dip_config['last_check_date'])
            time_since_last_check = datetime.now() - last_check
            minutes = (time_since_last_check.seconds // 60) % 60
            if minutes < 30:
                logger.info(f'Waiting {minutes} minutes to check again for dips in {symbol}')
                return

        change_from_last_order = (ticker['ask'] / last_order.price - 1) * 100
        if change_from_last_order < -dip_config['min_additional_drop_pct']:
            asset = symbol.split('/')[0]
            quote_ccy = symbol.split('/')[1]
            price = ticker['ask']
            cost = last_order.cost + dip_config['additional_drop_cost_increase']
            order = None
            try:
                order = crypto.place_buy_order(exchange, user_id, symbol, price, cost, 
                                                'market', Strategy.BUY_THE_DIPS, is_dummy, dry_run)
            except InsufficientFunds:
                database.update_last_check(self.user_account.user_id, symbol, Strategy.BUY_THE_DIPS, 'Insufficient funds')
                logger.info('Insufficient funds')
                quote_ccy = symbol.split('/')[1]
                base_ccy = symbol.split('/')[0]
                msg = f'Insufficient funds to buy {cost:.1f} {quote_ccy} of {base_ccy}. Trying again in 30 minutes'
                self.user_account.telegram_bot.send_msg(msg)
                return None
                
            if order:
                database.update_last_check(self.user_account.user_id, symbol, Strategy.BUY_THE_DIPS, 'Order placed')
                msg = (f'Buying {order["cost"]:,.2f} {quote_ccy} of {asset} @ {price:,.2f}. '
                    f'Current price is {change_from_last_order:.2f}% from the previous buy order')
                
                if is_dummy:
                    msg += '. (Running in simulation mode, balance was not affected)'
            else:
                database.update_last_check(self.user_account.user_id, symbol, Strategy.BUY_THE_DIPS, 'No action')

            logger.info(msg)
            if self.user_account.notify_to_telegram:
                self.user_account.telegram_bot.send_msg(msg)
            return order
        return None

    def buy_dips(self, symbols_stats: dict, dry_run: bool):
        """
        Place orders for buying dips
        """
        exchange = self.user_account.exchange
        for symbol, dip_config in self.user_account.dips_config.items():
            ticker = exchange.fetch_ticker(symbol)
            order = self._buy_initial_drop(ticker, dip_config, symbols_stats, dry_run)
            
            if order is None:
                order = self._buy_additional_drop(ticker, dip_config, dry_run)
            
            if order is not None:
                database.save_order(order, Strategy.BUY_THE_DIPS)
