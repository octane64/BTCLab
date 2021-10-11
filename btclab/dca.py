import logging
from datetime import datetime, timedelta
from dateutil import parser 
from ccxt.base.errors import InsufficientFunds

from common import Strategy
import database
from users import Account
import crypto


logger = logging.getLogger(__name__)

def days_to_buy(symbol: str, user_account: Account, is_dummy: bool) -> int:
    """
    Returns the number of days left to place a new buy order in a 
    dollar-cost-average (dca) strategy. 
    """
    time_since_last_dca = user_account.time_since_last_order(symbol, Strategy.DCA, is_dummy)
    if time_since_last_dca is None:
        days_left = 0
    else:
        seconds_in_a_day = 86400
        days_left = user_account.dca_config[symbol]['frequency'] - \
            (time_since_last_dca.total_seconds() / seconds_in_a_day)

    return max(days_left, 0)


def get_dca_buy_msg(order):
    """
    Returns a message with the resume of a dca operation
    """

    msg = f'Periodic buys: buying {order["cost"]:.2g} of {order["symbol"]} @ {order["price"]:,.5g}'
    if order['is_dummy']:
        msg += '. (Simulation)'
    return msg


def get_dca_summary(user_account: Account, dry_run: bool) -> str:
    if len(user_account.dca_config) == 0:
        return 'No DCA configuration found'
    
    msg = 'Next periodic purchases:'
    for symbol, config in user_account.dca_config.items():
        is_dummy = dry_run or config['is_dummy'] 
        days_remaining = days_to_buy(symbol, user_account, is_dummy)
        base_ccy = symbol.split('/')[0]
        quote_ccy = symbol.split('/')[1]

        if days_remaining > 0:
            next_date = datetime.now() + timedelta(days=days_remaining)
            msg += f'\n - {config["order_cost"]:g} {quote_ccy} of {base_ccy} on {next_date:%d-%m-%Y}'
    return msg


def buy(user_account: Account, dry_run: bool):
    for symbol, config in user_account.dca_config.items():
        cost = config['order_cost']
        user_id = user_account.user_id
        is_dummy = config['is_dummy'] or dry_run
        days_left = days_to_buy(symbol, user_account, is_dummy)
        
        if days_left != 0:
            time_remaining = f'{days_left/24:.0f} horas' if days_left <= 1 else f'{days_left:.1f} days'
            msg = f'Next purchase of {symbol} will occur in {time_remaining}'
            logger.info(msg)
            continue

        if config['last_check_result'] == 'Insufficient funds':
            last_check = parser.parse(config['last_check_date'])
            time_since_last_check = datetime.utcnow() - last_check
            minutes = (time_since_last_check.total_seconds() // 60) % 60
            if minutes < 30:
                logger.info(f'Waiting {minutes} minutes to check again for dips in {symbol} after insufficient funds')
                continue

        try:
            order = crypto.place_buy_order(exchange=user_account.exchange, 
                                            symbol=symbol, 
                                            price=None, 
                                            order_cost=cost, 
                                            order_type='market', 
                                            strategy=Strategy.DCA,
                                            is_dummy=config['is_dummy'],
                                            dry_run=dry_run,
                                            user_id=user_id)
        except InsufficientFunds:
            database.update_last_check(user_account.user_id, symbol, Strategy.DCA, 'Insufficient funds')
            quote_ccy = symbol.split('/')[1]
            base_ccy = symbol.split('/')[0]
            msg = f'Insufficient funds to buy {cost:.1f} {quote_ccy} of {base_ccy}. Trying again in 30 minutes'
            logger.info(msg)
            user_account.telegram_bot.send_msg(msg)
            continue

        if order:
            msg = get_dca_buy_msg(order)
            logger.info(msg)
            user_account.telegram_bot.send_msg(msg)
            database.save_order(order, Strategy.DCA)
            database.update_last_check(user_account.user_id, symbol, Strategy.DCA, 'Order placed')
        else:
            database.update_last_check(user_account.user_id, symbol, Strategy.DCA, 'No action')
