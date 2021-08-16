import yaml
from enum import Enum
from datetime import datetime
from typing import List
from retry import retry
from logconf import logger
from ccxt.base.errors import InsufficientFunds, BadSymbol, NetworkError


class Strategy(Enum):
    BUY_THE_DIPS = 'dip'
    DCA = 'dca'


def get_config():
    """Returns a dictionary with the info in config.yaml"""
    with open('./btclab/config.yaml', 'r') as stream:
        try:
            config = yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            print(exc)
    return config


@retry(NetworkError, delay=15, jitter=5, logger=logger)
def get_non_supported_symbols(exchange, symbols: List) -> set:
    exchange.load_markets()
    return set(symbols).difference(set(exchange.symbols))


@retry(NetworkError, delay=15, jitter=5, logger=logger)
def get_balance(exchange, currency: str) -> float:
    balance = exchange.fetch_balance()[currency]['free']
    return balance


def get_dummy_order(symbol, order_type, side, price, cost) -> dict:
    """Returns a dictionary with the information of a dummy order. 
    The structure is the same as the one returned by the create_order function from ccxt library
    https://ccxt.readthedocs.io/en/latest/manual.html#orders
    """
    right_now = datetime.now()
    order = {
            'id': 'DummyOrder',
            'datetime': right_now.isoformat(),
            'timestamp': datetime.timestamp(right_now), # order placing/opening Unix timestamp in milliseconds
            'lastTradeTimestamp': datetime.timestamp(right_now), # Unix timestamp of the most recent trade on this order
            'status': 'closed',
            'symbol': symbol,
            'type': order_type,
            'side': side,
            'price': price,
            'average': price,
            'amount': cost / price, # 
            'filled': cost / price,
            'remaining': 0,  # Asumes the whole order amount got filled (Market order)
            'cost': cost
    }
    
    return order
  

def bought_within_the_last(hours: float, symbol:str, orders: dict) -> bool:
    """
    Returns true if symbol was bought within the last hours, false otherwise
    """
    if symbol not in orders:
        return False    
    
    now = datetime.now()
    timestamp = orders[symbol]['timestamp']
    bought_on = datetime.fromtimestamp(timestamp/1000)
    diff = now - bought_on
    return diff.days <= hours


@retry(NetworkError, delay=15, jitter=5, logger=logger)
def place_buy_order(exchange, symbol, price, order_cost, order_type, dry_run=True):
    """ Returns a dictionary with the information of the order placed
    """

    if dry_run:
        params = {
            'symbol': symbol.replace('/', ''), 
            'side': 'buy', 
            'type': 'market', 
            'quoteOrderQty': order_cost
        }
        order = exchange.private_post_order_test(params)
        
        if order:
            order = get_dummy_order(symbol, order_type, 'buy', price, order_cost)
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
    