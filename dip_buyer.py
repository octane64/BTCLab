import time
import utils
import ccxt
import click
import pickle
from ccxt.base.errors import InsufficientFunds, BadSymbol
import secrets


chat_id = getattr(secrets, 'keys')['Telegram chat id']
binance_key = getattr(secrets, 'keys')['binance_key']
binance_secret = getattr(secrets, 'keys')['binance_secret']


def get_biggest_drop(exchange, symbols, quote_currency='USDT') -> dict:
    """
    Returns a dictionary with info of the ticker with the biggest drop in price (percent-wise) in the last 
    24 hours, None in case any of the symbols have depreciated (<0) in that time
    """
    ref_pct_change = 0
    biggest_drop = None

    for symbol in symbols:
        ticker = exchange.fetch_ticker(f'{symbol}/{quote_currency}')
        pct_change_24h = ticker['percentage']
        
        if pct_change_24h < ref_pct_change:
            biggest_drop = {'Ticker': ticker['symbol'],
                            'Last price': ticker['last'],
                            'Pct change': pct_change_24h
            }
            ref_pct_change = pct_change_24h

    return biggest_drop


def get_balance(exchange, currency: str) -> float:
    balance = exchange.fetch_balance()[currency]['free']
    return balance


def place_order(exchange, order_info, dummy_mode=False):
    symbol = order_info['Ticker']
    order_type = 'limit'  # or 'market'
    side = 'buy'  # or 'buy'
    price = order_info['Last price']
    usd_order_amount = 11
    amount = usd_order_amount / price

    # extra params and overrides if needed
    params = {
        'test': dummy_mode,  # test if it's valid, but don't actually place it
    }

    try:
        order = exchange.create_order(symbol, order_type, side, amount, price, params)
    except InsufficientFunds:
        try:
            symbol = symbol.replace('USDT', 'USDC')
            order = exchange.create_order(symbol, order_type, side, amount, price, params)
        except BadSymbol: #Tried with balance in USDC but pair not available
            raise InsufficientFunds
            
    return order


def better_than_previous(new_order, previous_order, min_discount: float = 0.03) -> bool:
    discount = abs(new_order['Last price'] / previous_order['Last price'] - 1)
    return discount > min_discount


def short_summary(order) -> str:
    """"
        Returns a brief description of an order
        order param is a dict with the structure defined in 
        https://github.com/ccxt/ccxt/wiki/Manual#order-structure
    """
    action = 'Bought' if order['side'] == 'buy' else 'Sold'

    # Ex: Bought 0.034534 BTC/USDT @ 56,034.34
    msg = f'{action} {order["filled"]:.8f} {order["symbol"]} @ {order["average"]:,.2f}'
    # utils.send_msg(chat_id, msg)
    return msg
    

@click.command()
@click.option('--freq', '-f', default=5, help='Frequency in minutes for checking the market')
@click.option('--min_drop', '-d', default=10, help='Buy only if 24h drop surpass this level')
def main(freq, min_drop):
    binance = ccxt.binance({'apiKey': binance_key, 'secret': binance_secret, 'enableRateLimit': True})
    symbols = 'BTC ETH DOT XMR BCH'.split()

    orders = {}

    while True:
        # What symbol has the biggest drop in the last 24 hours?
        biggest_drop = get_biggest_drop(binance, symbols)
        
        if biggest_drop is None:
            print(f'None of the pairs has dropped in the last 24 hours. Checking again in {freq} minutes...')
            time.sleep(freq * 60)
            continue
        else:
            print(f'{biggest_drop["Ticker"]} is down {biggest_drop["Pct change"]}% from the last 24 hours')

        if biggest_drop['Pct change'] < -min_drop:
            previous_order = orders.get(biggest_drop['Ticker'])
            if previous_order is None or better_than_previous(biggest_drop, previous_order):
                try:
                    order = place_order(binance, biggest_drop, dummy_mode=True)
                    # TODO Notify order placed to chat
                    print(order)
                except InsufficientFunds:
                    print('Insufficient funds. Trying again in 15 minutes...')
                    time.sleep(15 * 60)
                    continue
                    # TODO Notify fail to place order because insufficient funds to chat
                else:
                    orders[biggest_drop['Ticker']] = biggest_drop
            else:
                ticker = biggest_drop['Ticker']
                s = ticker[:ticker.find('/')]
                symbols.remove(s)
                continue

        time.sleep(freq * 60)


if __name__ == '__main__':
    print('Started monitoring crypto prices')
    main()