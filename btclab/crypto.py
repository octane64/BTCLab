from datetime import datetime
from ccxt.base.errors import InsufficientFunds, BadSymbol


def get_biggest_drop(exchange, symbols, quote_currency='USDT') -> dict:
    """
    Returns a dictionary with info of the ticker with the biggest drop in price (percent-wise) 
    in the last 24 hours, None in case any of the symbols have depreciated (<0) in that time
    """
    ref_pct_change = 0
    biggest_drop = None

    for symbol in symbols:
        ticker = exchange.fetch_ticker(f'{symbol}/{quote_currency}')
        pct_chg_24h = ticker['percentage']

        if pct_chg_24h < ref_pct_change:
            biggest_drop = {
                'symbol': ticker['symbol'],
                'price': ticker['last'],
                '24h_pct_chg': pct_chg_24h,
            }
            ref_pct_change = pct_chg_24h

    return biggest_drop


def get_balance(exchange, currency: str) -> float:
    balance = exchange.fetch_balance()[currency]['free']
    return balance


def get_dummy_order(symbol, order_type, side, price, amount) -> dict:
    """Returns a dictionary with the order information. 
    
    The sctructure used is the same that the one returned by the create_order function from ccxt library
    """
    timestamp = datetime.now().isoformat()
    order = {
            'id': 'DummyOrder',
            'datetime': timestamp,
            'lastTradeTimestamp': timestamp,
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
  

def place_order(exchange, order_info, amount_in_usd, dry_run=True):
    # Returns a dictionary with the information of the order placed
    
    symbol = order_info['symbol']
    order_type = 'limit'  # or 'market'
    side = 'buy'  # or 'sell'
    price = order_info['price']
    usd_order_amount = amount_in_usd
    amount = usd_order_amount / price
    
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
    action = "Bought" if order["side"] == "buy" else "Sold"

    # Ex: Bought 0.034534 BTC/USDT @ 56,034.34
    msg = (
        f'{order["symbol"]} is down {pct_chg:.2f}% from the last 24'
        f'hours. {action} {order["filled"]:.6f} @ {order["average"]:,.2f}'
    )
    return msg


def is_better_than_previous(new_order, previous_order, min_discount) -> bool:
    assert min_discount > 0, 'min_discount should be a positive number'
    
    discount = new_order['price'] / previous_order['price'] - 1
    return discount < 0 and abs(discount) > min_discount/100