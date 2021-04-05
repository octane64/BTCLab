import time
import requests
import ccxt
import secrets


bot_token = secrets.keys('Telegram bot token') #OctaneBot
chat_id = secrets.keys('Telegram chat id')

def send_msg(chat_id, msg):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage?chat_id={chat_id}&text={msg}"

    # send the msg
    requests.get(url)

binance_key = secrets.keys('binance_key')
binance_secret = secrets.keys('binance_secret')


def main():
    binance = ccxt.binance({'apiKey': binance_key, 'secret': binance_secret, 'enableRateLimit': True})
    
    while True:
        ticker = binance.fetch_ticker('BTC/USDC')
        balance = binance.fetch_balance()
        usdc_balance = balance['USDC']['free']
        usdt_balance = balance['USDT']['free']
        pct_change_24h = ticker['percentage']

        if pct_change_24h < -5.5:
            msg1 = f'BTC/USDC down {pct_change_24h}% from last 24h'
            print(msg1)
            symbol = 'BTC/USDC'  
            order_type = 'limit'  # or 'market'
            side = 'buy'  # or 'buy'
            price = ticker['last'] - 10  # or None
            amount = 11 / price

            # extra params and overrides if needed
            # params = {
            #     'test': False,  # test if it's valid, but don't actually place it
            # }

            # order = binance.create_order(symbol, order_type, side, amount, price)
            # order = binance.create_order(symbol, type, side, amount, price)
            
            # print(order)
            msg2 = msg1 + '\n' + f'Dummy trade: Buy {amount:.08f} {symbol} @ {price:,.2f}'
            send_msg(chat_id, msg2)
            time.sleep(60 * 5)

        time.sleep(30)


if __name__ == '__main__':
    print('Started monitoring crypto prices')
    main()