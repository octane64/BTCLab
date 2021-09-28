import logging
from datetime import datetime
from typing import List, Optional
from retry import retry
from ccxt.base.exchange import Exchange
from ccxt.base.errors import InsufficientFunds, BadSymbol, NetworkError

from btclab.common import Strategy
from btclab.order import Order

logger = logging.getLogger(__name__)


@retry(NetworkError, delay=15, jitter=5, logger=logger)
def get_non_supported_symbols(exchange, symbols: List) -> set:
    exchange.load_markets()
    return set(symbols).difference(set(exchange.symbols))





@retry(NetworkError, delay=15, jitter=5, logger=logger)
def place_buy_order(exchange: Exchange, user_id: int, symbol: str, price: float, order_cost: float, order_type: str,
        strategy: Strategy, is_dummy: bool = False, dry_run: bool = False):
    """ 
    Returns a dictionary with the information of the order placed
    """

    if is_dummy or dry_run:
        params = {
            'symbol': symbol.replace('/', ''), 
            'side': 'buy', 
            'type': 'market', 
            'quoteOrderQty': order_cost
        }
        
        if price is None:
            price = exchange.fetch_ticker(symbol)['last']
        order = exchange.private_post_order_test(params) # TODO Check if necessary
        
        if order is not None:
            order = Order.get_dummy_order(user_id, symbol, order_type, 'buy', price, order_cost, strategy)
        return order

    if order_type == 'market':
        if exchange.has['createMarketOrder']:
            exchange.options['createMarketBuyOrderRequiresPrice'] = False
            params = {'quoteOrderQty': order_cost}
            order = exchange.create_market_buy_order(symbol, order_cost, params)
        else:
            exchange.options['createMarketBuyOrderRequiresPrice'] = True
            amount = order_cost / price
            order = exchange.create_market_buy_order(symbol, amount, price)
    else:
        amount = order_cost / price
        order = exchange.create_limit_buy_order(symbol, amount, price)

    order['is_dummy'] = is_dummy or dry_run
    order['user_id'] = user_id

    return order
    

def insufficient_funds(exchange, symbol, order_cost):
    """
    Returns the balance in quote currency of symbol when insufficient to cover order cost, zero otherwise
    """
    quote_ccy = symbol.split('/')[1]
    balance = exchange.fetch_balance()[quote_ccy]['free']
    
    if balance < order_cost:
        return balance
    return 0


def get_insufficient_funds_msg(symbol, order_cost, balance, retry_after):
    asset = symbol.split('/')[0]
    quote_ccy = symbol.split('/')[1]
    msg = (
        f'Insufficient funds. Next order will try to buy {order_cost:,.0f} {quote_ccy} '
        f'of {asset} but {quote_ccy} balance is {balance:,.2f}. Trying again in '
        f'{retry_after} minutes...'
    )
    return msg       
