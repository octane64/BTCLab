import logging
from typing import Optional
from ccxt import Exchange
from ccxt.base.errors import InsufficientFunds, NetworkError, AuthenticationError
from dataclasses import dataclass
from datetime import datetime
from dateutil import parser
from retry import retry

import database
import crypto
from common import Strategy
from users import Account
from order import Order


logger = logging.getLogger(__name__)


def buy_initial_drop(user_account: Account, symbol: str, dip_config: dict, symbols_stats: dict, dry_run: bool):
    """
    Places a new buy order if at current price the change in the last 24h represents a drop
    that surpasses the min_drop limit and the symbol has not been bought in the last 24 hours
    """
    
    if dip_config['min_drop_units'] == 'SD':
        min_drop = dip_config['min_drop_value'] * symbols_stats[symbol]['std_dev'] * -100
    else:
        min_drop = dip_config['min_drop_value'] * -1
    
    if dip_config['last_check_result'] == 'Insufficient funds':
        last_check = parser.parse(dip_config['last_check_date'])
        time_since_last_check = datetime.utcnow() - last_check
        minutes = time_since_last_check.total_seconds() / 60
        if minutes < 30:
            logger.info(f'Waiting {minutes} more minutes to check again for dips in {symbol}')
            return

    try:
        ticker = user_account.exchange.fetch_ticker(symbol)
    except AuthenticationError:
        logger.error('Authentication error')
        return

    if not ticker['percentage'] < min_drop:
        database.update_last_check(user_account.user_id, symbol, Strategy.BUY_THE_DIPS, 'No action')
        msg = f'{symbol}: Last 24h change is {ticker["percentage"]:+.2f}%, min drop of {min_drop:.2f}% not met'
        logger.info(msg)
        return
    
    asset = symbol.split('/')[0]
    quote_ccy = symbol.split('/')[1]
    price = ticker['last']
    cost = dip_config['order_cost']
    is_dummy = dip_config['is_dummy'] or dry_run
    order = None

    last_dca = database.get_latest_order(user_account.user_id, symbol, dip_config['is_dummy'], Strategy.DCA)
    if last_dca is None or last_dca.price > price:
        try:
            order = crypto.place_buy_order(exchange=user_account.exchange, 
                                            user_id=user_account.user_id,
                                            symbol=symbol, 
                                            price=price,
                                            order_cost=cost, 
                                            order_type='market', 
                                            strategy=Strategy.BUY_THE_DIPS,
                                            is_dummy=is_dummy,
                                            dry_run=dry_run)
        except InsufficientFunds:
            database.update_last_check(user_account.user_id, symbol, Strategy.BUY_THE_DIPS, 'Insufficient funds')
            logger.info('Insufficient funds')
            quote_ccy = symbol.split('/')[1]
            base_ccy = symbol.split('/')[0]
            msg = f'Insufficient funds to buy {cost:.1f} {quote_ccy} of {base_ccy}. Trying again in 30 minutes'
            user_account.telegram_bot.send_msg(msg)
            return None

    msg = ''
    if order:
        database.update_last_check(user_account.user_id, symbol, Strategy.BUY_THE_DIPS, 'Order placed')
        msg = (f'Buying {order["cost"]:,.2f} {quote_ccy} of {asset} @ {price:,.6g}. '
                f'Drop in last 24h is {ticker["percentage"]:+.2f}%')
        if is_dummy:
            msg += '. (Running in simulation mode, balance was not affected)'
    else:
        database.update_last_check(user_account.user_id, symbol, Strategy.BUY_THE_DIPS, 'No action')
    
    logger.info(msg)
    if user_account.notify_to_telegram:
        user_account.telegram_bot.send_msg(msg)
    return order
    

def buy_additional_drop(user_account: Account, symbol: str, dip_config: dict, dry_run: bool) -> Optional[Order]:
    """
    Places a new buy order if symbol has been bought recently and last 24h drop 
    surpasses the min_next_drop limit
    """
    user_id = user_account.user_id
    exchange = user_account.exchange
    is_dummy = dip_config['is_dummy'] or dry_run
    last_order = database.get_latest_order(user_id, symbol, is_dummy, Strategy.BUY_THE_DIPS)
    if last_order is None:
        return None
    
    if dip_config['last_check_result'] == 'Insufficient funds':
        last_check = parser.parse(dip_config['last_check_date'])
        time_since_last_check = datetime.utcnow() - last_check
        minutes = (time_since_last_check.total_seconds() // 60) % 60
        if minutes < 30:
            logger.info(f'Waiting {minutes} minutes to check again for dips in {symbol}')
            return

    try:
        ticker = user_account.exchange.fetch_ticker(symbol)
    except AuthenticationError:
        logger.error('Authentication error')
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
            database.update_last_check(user_account.user_id, symbol, Strategy.BUY_THE_DIPS, 'Insufficient funds')
            logger.info('Insufficient funds')
            quote_ccy = symbol.split('/')[1]
            base_ccy = symbol.split('/')[0]
            msg = f'Insufficient funds to buy {cost:.1f} {quote_ccy} of {base_ccy}. Trying again in 30 minutes'
            user_account.telegram_bot.send_msg(msg)
            return None
            
        if order:
            database.update_last_check(user_account.user_id, symbol, Strategy.BUY_THE_DIPS, 'Order placed')
            msg = (f'Buying {order["cost"]:,.2f} {quote_ccy} of {asset} @ {price:,.2f}. '
                f'Current price is {change_from_last_order:.2f}% from the previous buy order')
            
            if is_dummy:
                msg += '. (Running in simulation mode, balance was not affected)'
        else:
            database.update_last_check(user_account.user_id, symbol, Strategy.BUY_THE_DIPS, 'No action')

        logger.info(msg)
        if user_account.notify_to_telegram:
            user_account.telegram_bot.send_msg(msg)
        return order
    return None


@retry(NetworkError, delay=15, jitter=5, logger=logger)
def buy_dips(user_account: Account, symbols_stats: dict, dry_run: bool):
    """
    Place orders for buying dips
    """
    for symbol, dip_config in user_account.dips_config.items():
        order = buy_initial_drop(user_account, symbol, dip_config, symbols_stats, dry_run)
        
        if order is None:
            order = buy_additional_drop(user_account, symbol, dip_config, dry_run)
        
        if order is not None:
            database.save_order(order, Strategy.BUY_THE_DIPS)
