import time
import ccxt
from datetime import datetime
from ccxt.base.errors import InsufficientFunds, BadSymbol
import components.common.APIHelper as APIHelper
import components.common.LogicHelper as LogicHelper
import components.common.Constants as Constants
import components.common.FileHelper as FileHelper
import components.common.NotificationsHelper as im
import components.common.OrdersHelper as oh


def print_header(config):
    symbols = ', '.join(config['General']['tickers'])
    min_additional = config['General']['min_additional_drop']
    dry_run = config['General']['dry_run']
    title = 'Crypto prices monitor running'
    print(f'\n{"-" * len(title)}\n{title}\n{"-" * len(title)}')
    if dry_run:
        print('Running in summulation mode\n')
    
    print(f'1) Tracking price changes in: {symbols}')
    print(f'2) Any drop of {config["General"]["min_initial_drop"]}% or more will be bought')
    print(f'3) Any further drop of more than {min_additional}% (relative to previous buy) will also be bought')
    print('')


def main():
    config = FileHelper.get_config()
    freq = config["General"]["frequency"]
    min_drop = config['General']['min_initial_drop']
    amount_usd = config['General']['order_amount_usd']
    bot_token = config['IM']['telegram_bot_token']
    chat_id = config['IM']['telegram_chat_id']
    retry_after = config['General']['retry_after']

    print_header(config)
    binance = ccxt.binance(
        {
            'apiKey': config['Exchange']['api_key'],
            'secret': config['Exchange']['api_secret'],
            'enableRateLimit': True,
        }
    )
    orders = {}

    while True:
        # What symbol has the biggest drop in the last 24 hours?
        biggest_drop = APIHelper.get_biggest_drop(binance, config['General']['tickers'])

        if biggest_drop is None:
            print(f'No new drops. Checking again in {freq} minutes...')
            time.sleep(freq * 60)
            continue

        if biggest_drop['24h_pct_chg'] < -min_drop:
            previous_order = orders.get(biggest_drop['symbol'])
            if previous_order is None or LogicHelper.is_better_than_previous(biggest_drop, previous_order, min_drop):
                try:
                    order = APIHelper.place_order(binance, biggest_drop, amount_usd, dry_run=True)
                except InsufficientFunds:
                    print(f'Insufficient funds. Trying again in {retry_after} minutes...')
                    time.sleep(retry_after * 60)
                    msg = f'Insufficient funds while trying to buy {biggest_drop["symbol"]}'
                    im.send_msg(bot_token, chat_id, )
                    continue
                else:
                    msg = oh.short_summary(order, biggest_drop['24h_pct_chg'])
                    im.send_msg(bot_token, chat_id, msg)
                    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    print(f'\n{now} - {msg}')
                    orders[biggest_drop['symbol']] = order
                    # save(orders)

        # time.sleep(freq * 30)
        time.sleep(5)


if __name__ == '__main__':
    main()
