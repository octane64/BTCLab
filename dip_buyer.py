import time
import utils
import ccxt
import pickle
from ccxt.base.errors import InsufficientFunds, BadSymbol
import secrets


chat_id = getattr(secrets, 'keys')['Telegram chat id']
binance_key = getattr(secrets, 'keys')['binance_key']
binance_secret = getattr(secrets, 'keys')['binance_secret']

MIN_DIP_PCT = -12 # Minimum 24h pct change to start buying


def get_biggest_drop(exchange, symbols='BTC ETH ADA DOT BCH XMR'.split(), quote_currency='USDT') -> dict:
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


def better_than_previous_order(new_order, previous_order, min_discount: float = 0.03) -> bool:
    discount = abs(new_order['Last price'] / previous_order['Last price'] - 1)
    return discount > min_discount


def get_order_details(order) -> str:
    
    
    msg = f'Bought {amount:.08f} {symbol} @ {price:,.2f}. 24h change was {order_info["Pct change"]}%'
    utils.send_msg(chat_id, msg)
    print(msg)
    

def main():
    binance = ccxt.binance({'apiKey': binance_key, 'secret': binance_secret, 'enableRateLimit': True})
    symbols = 'BTC ETH DOT XMR'.split()

    orders = {}
    i = 0

    while True:
        if i < 30:
            biggest_drop = get_biggest_drop(binance, symbols)
        else:
            biggest_drop = get_biggest_drop(binance) # Run whith all default symbols
            i = 0
        
        print(f'{biggest_drop["Ticker"]} is down {biggest_drop["Pct change"]} from the last 24 hours')

        # usdt_balance = get_balance(binance, 'USDT')
        if biggest_drop['Pct change'] < MIN_DIP_PCT:
            previous_order = orders.get(biggest_drop['Ticker'])
            # msg1 = f'{biggest_drop["Ticker"]} down {biggest_drop["Pct change"]}% from last 24h'
            if previous_order is None or better_than_previous_order(biggest_drop, previous_order):
                try:
                    order = place_order(binance, biggest_drop)
                except InsufficientFunds:
                    print('Insufficient funds. Trying again in 15 minutes...')
                    time.sleep(15 * 60)
                    continue
                except BadSymbol:
                    ticker = biggest_drop['Ticker']
                    s = ticker.replace('USDT', 'USDC')
                    s = ticker[:ticker.find('/')]
                    symbols.remove(s)
                    print(f'{s}/USDC pair not available at exchange. Removing coin temporarily from initial list...')
                    i += 1
                    continue
                orders[biggest_drop['Ticker']] = biggest_drop
            else:
                ticker = biggest_drop['Ticker']
                s = ticker[:ticker.find('/')]
                symbols.remove(s)
                i += 1
                continue

        time.sleep(60)


if __name__ == '__main__':
    print('Started monitoring crypto prices')
    main()