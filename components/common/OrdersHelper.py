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
    