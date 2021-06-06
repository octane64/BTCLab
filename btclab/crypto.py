from datetime import datetime
from typing import List
from retry import retry
from logconf import logger
from ccxt.base.errors import InsufficientFunds, BadSymbol, NetworkError


@retry(NetworkError, delay=15, jitter=5, logger=logger)
def get_non_supported_symbols(exchange, symbols: List) -> set:
    exchange.load_markets()
    return set(symbols).difference(set(exchange.symbols))


@retry(NetworkError, delay=15, jitter=5, logger=logger)
def get_balance(exchange, currency: str) -> float:
    balance = exchange.fetch_balance()[currency]['free']
    return balance


def get_dummy_order(symbol, order_type, side, price, amount) -> dict:
    """Returns a dictionary with the information of a dummy order. 
    The structure is the same as the one returned by the create_order function from ccxt library
    """
    right_now = datetime.now()
    order = {
            'id': 'DummyOrder',
            'datetime': right_now.isoformat(),
            'timestamp': datetime.timestamp(right_now),
            'lastTradeTimestamp': datetime.timestamp(right_now),
            'status': 'closed',
            'symbol': symbol,
            'type': order_type,
            'side': side,
            'price': price,
            'average': price,
            'amount': amount,
            'filled': amount,
            'remaining': 0  # Asumes the whole order amount got filled (Market order)
    }
    
    return order
  

def bought_less_than_24h_ago(symbol:str, orders: dict, dry_run: bool) -> bool:
    """Returns true if symbol was bought within the last 24 hours, false otherwise
    """
    if symbol in orders and ((dry_run == True and orders[symbol]['id'] == 'DummyOrder') or \
                                not dry_run and orders[symbol]['id'] != 'DummyOrder'):
            now = datetime.now()
            timestamp = orders[symbol]['timestamp']
            if '.' not in str(timestamp):
                timestamp /= 1000
            bought_on = datetime.fromtimestamp(timestamp)
            diff = now - bought_on
            return diff.days <= 1
    return False 


@retry(NetworkError, delay=15, jitter=5, logger=logger)
def place_order(exchange, symbol, price, amount_in_usd, previous_orders, increase_amount_by=0, dry_run=True):
    """ Returns a dictionary with the information of the order placed
    """
    
    order_type = 'limit'  # or 'market'
    side = 'buy'  # or 'sell'

    if bought_less_than_24h_ago(symbol, previous_orders, dry_run) and increase_amount_by > 0:
        prev_amount_in_usd = previous_orders[symbol]['amount'] * price
        amount_in_usd = prev_amount_in_usd + increase_amount_by
    
    amount = amount_in_usd / price # TODO Fix for symbols with quote a quote currency that is not USD or equivalents
    if dry_run:
        order = get_dummy_order(symbol, order_type, side, price, amount)
    else:
        # extra params and overrides if needed
        params = {'test': dry_run,}  # test if it's valid, but don't actually place it

        try:
            order = exchange.create_order(symbol, order_type, side, amount, price, params)
        except InsufficientFunds:
            try:
                symbol = symbol.replace('USDT', 'USDC')
                order = exchange.create_order(
                    symbol, order_type, side, amount, price, params
                )
            except BadSymbol:  # Tried with balance in USDC but pair not available
                raise InsufficientFunds

    return order


def short_summary(order, pct_chg) -> str:
    """
    Returns a brief description of an order
    order param is a dict with the structure defined in
    https://github.com/ccxt/ccxt/wiki/Manual#order-structure
    """
    action = "Buying" if order["side"] == "buy" else "Sold"

    # Ex: Buying 0.034534 BTC/USDT @ 56,034.34
    msg = (
        f'{order["symbol"]} is down {pct_chg:.2f}% from the last 24 '
        f'hours: {action} {order["amount"]:.6f} @ {order["price"]:,.2f}'
    )
    return msg


def is_better_than_previous(new_order, previous_order, min_discount) -> bool:
    """Returns True if price in new_order is better (min_discount cheaper) 
    than the price in previous_order, False otherwise
    """
    assert min_discount > 0, 'min_discount should be a positive number'
    
    discount = new_order['price'] / previous_order['price'] - 1
    return discount < 0 and abs(discount) > min_discount/100