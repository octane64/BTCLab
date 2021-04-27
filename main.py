import time
import ccxt
import crypto
import utils
from datetime import datetime
from ccxt.base.errors import InsufficientFunds, BadSymbol


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
    config = utils.get_config()
    freq = config["General"]["frequency"]
    min_drop = config['General']['min_initial_drop']
    amount_usd = config['General']['order_amount_usd']
    bot_token = config['IM']['telegram_bot_token']
    chat_id = config['IM']['telegram_chat_id']
    retry_after = config['General']['retry_after']
    dry_run = config['General']['dry_run']

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
        biggest_drop = crypto.get_biggest_drop(binance, config['General']['tickers'])

        if biggest_drop is None:
            print(f'No new drops. Checking again in {freq} minutes...')
            time.sleep(freq * 60)
            continue

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if biggest_drop['24h_pct_chg'] < -min_drop:
            previous_order = orders.get(biggest_drop['symbol'])
            
            if crypto.is_better_than_previous(biggest_drop, previous_order, min_drop):
                try:
                    order = crypto.place_order(binance, biggest_drop, amount_usd, dry_run=dry_run)
                except InsufficientFunds:
                    print(f'Insufficient funds. Trying again in {retry_after} minutes...')
                    time.sleep(retry_after * 60)
                    msg = f'Insufficient funds while trying to buy {biggest_drop["symbol"]}'
                    utils.send_msg(bot_token, chat_id, )
                    continue
                else:
                    msg = crypto.short_summary(order, biggest_drop['24h_pct_chg'])
                    utils.send_msg(bot_token, chat_id, msg)
                    print(f'\n{now} - {msg}')
                    orders[biggest_drop['symbol']] = order
                    # save(orders)
        else:
            print(f'{now} - No big discounts. Checking again in {freq} minutes')

        # time.sleep(freq * 30)
        time.sleep(freq * 60)


if __name__ == '__main__':
    main()
