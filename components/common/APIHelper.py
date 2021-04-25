import ccxt
from ccxt.base.errors import InsufficientFunds, BadSymbol


def get_biggest_drop(exchange, symbols, quote_currency="USDT") -> dict:
    """
    Returns a dictionary with info of the ticker with the biggest drop in price (percent-wise) in the last
    24 hours, None in case any of the symbols have depreciated (<0) in that time
    """
    ref_pct_change = 0
    biggest_drop = None

    for symbol in symbols:
        ticker = exchange.fetch_ticker(f"{symbol}/{quote_currency}")
        pct_change_24h = ticker["percentage"]

        if pct_change_24h < ref_pct_change:
            biggest_drop = {
                "Ticker": ticker["symbol"],
                "Last price": ticker["last"],
                "Pct change": pct_change_24h,
            }
            ref_pct_change = pct_change_24h

    return biggest_drop


def get_balance(exchange, currency: str) -> float:
    balance = exchange.fetch_balance()[currency]["free"]
    return balance


def place_order(exchange, order_info, dummy_mode=False):
    symbol = order_info["Ticker"]
    order_type = "limit"  # or 'market'
    side = "buy"  # or 'buy'
    price = order_info["Last price"]
    usd_order_amount = 11
    amount = usd_order_amount / price

    # extra params and overrides if needed
    params = {
        "test": dummy_mode,  # test if it's valid, but don't actually place it
    }

    try:
        order = exchange.create_order(symbol, order_type, side, amount, price, params)
    except InsufficientFunds:
        try:
            symbol = symbol.replace("USDT", "USDC")
            order = exchange.create_order(
                symbol, order_type, side, amount, price, params
            )
        except BadSymbol:  # Tried with balance in USDC but pair not available
            raise InsufficientFunds

    return order