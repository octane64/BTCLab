def to_short_summary(order) -> str:
    """ "
    Returns a brief description of an order
    order param is a dict with the structure defined in
    https://github.com/ccxt/ccxt/wiki/Manual#order-structure
    """
    action = "Bought" if order["side"] == "buy" else "Sold"

    # Ex: Bought 0.034534 BTC/USDT @ 56,034.34
    msg = f'{action} {order["filled"]:.8f} {order["symbol"]} @ {order["average"]:,.2f}'
    # utils.send_msg(chat_id, msg)
    return msg