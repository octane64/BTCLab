import yaml
from datetime import datetime
from typing import List
from retry import retry
from common import Strategy
from logconf import logger
from ccxt.base.exchange import Exchange
from ccxt.base.errors import InsufficientFunds, BadSymbol, NetworkError


@retry(NetworkError, delay=15, jitter=5, logger=logger)
def get_non_supported_symbols(exchange, symbols: List) -> set:
    exchange.load_markets()
    return set(symbols).difference(set(exchange.symbols))


def get_dummy_order(user_id, symbol, order_type, side, price, cost, strategy) -> dict:
    """Returns a dictionary with the information of a dummy order. 
    The structure is the same as the one returned by the create_order function from ccxt library
    https://ccxt.readthedocs.io/en/latest/manual.html#orders
    """
    right_now = datetime.now()
    ts = int(datetime.timestamp(right_now))
    order = {
            'id': ts,
            'timestamp': ts, # order placing/opening Unix timestamp in milliseconds
            'symbol': symbol,
            'type': order_type,
            'side': side,
            'price': price,
            'amount': cost / price, # 
            'cost': cost,
            'strategy': strategy.value,
            'is_dummy': int(True),
            'user_id': user_id
    }
    
    return order
  

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


@retry(NetworkError, delay=15, jitter=5, logger=logger)
def place_buy_order(exchange: Exchange, symbol: str, price: float, order_cost: float, 
                    order_type: str, strategy: Strategy, dry_run: bool = True):
    """ Returns a dictionary with the information of the order placed
    """

    if dry_run:
        params = {
            'symbol': symbol.replace('/', ''), 
            'side': 'buy', 
            'type': 'market', 
            'quoteOrderQty': order_cost
        }
        
        if price is None:
            price = exchange.fetch_ticker(symbol)['last']
        order = exchange.private_post_order_test(params)
        
        if order is not None:
            order = get_dummy_order(symbol, order_type, 'buy', price, order_cost, order_cost, strategy)
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