from datetime import datetime
from typing import List
from retry import retry
from logconf import logger
from ccxt.base.errors import InsufficientFunds, BadSymbol, NetworkError


@retry(NetworkError, tries=5, delay=10, backoff=2, logger=logger)
def get_unsupported_symbols(exchange, symbols: List) -> set:
    exchange.load_markets()
    return set(symbols).difference(set(exchange.symbols))


@retry(NetworkError, tries=5, delay=10, backoff=2, logger=logger)
def get_balance(exchange, currency: str) -> float:
    balance = exchange.fetch_balance()[currency]['free']
    return balance


def get_dummy_order(symbol, order_type, side, price, amount) -> dict:
    """Returns a dictionary with the order information. 
    
    The sctructure used is the same that the one returned by the create_order function from ccxt library
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
            'remaining': 0  # Asumes the whole order amount got filled in dry-run mode (Market order)
    }
    
    return order
  

@retry(NetworkError, tries=5, delay=10, backoff=2, logger=logger)
def place_order(exchange, symbol, price, amount_in_usd, dry_run=True):
    # Returns a dictionary with the information of the order placed
    
    order_type = 'limit'  # or 'market'
    side = 'buy'  # or 'sell'
    amount = amount_in_usd / price # TODO Fix for symbols with quote a quote currency that is not USD or equivalents
    
    if dry_run:
        order = get_dummy_order(symbol, order_type, side, price, amount)
    else:
        # extra params and overrides if needed
        params = {
            'test': dry_run,  # test if it's valid, but don't actually place it
        }

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
    """ "
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
    assert min_discount > 0, 'min_discount should be a positive number'
    
    discount = new_order['price'] / previous_order['price'] - 1
    return discount < 0 and abs(discount) > min_discount/100