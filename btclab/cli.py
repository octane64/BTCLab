import time
import ccxt
import typer
from btclab import crypto
from btclab import utils
from datetime import datetime
from ccxt.base.errors import InsufficientFunds


app = typer.Typer()
config = utils.get_config()

def print_header(freq, amount_usd, min_drop, min_additional_drop, dry_run):
    global config
    symbols = ', '.join(config['General']['tickers'])
    title = 'Crypto prices monitor running'
    print(f'\n{"-" * len(title)}\n{title}\n{"-" * len(title)}')
    if dry_run:
        print('Running in summulation mode\n')
    
    print(f'1) Tracking price changes in: {symbols} every {freq} minutes')
    print(f'2) Any drop of {min_drop}% or more will trigger a buy order of {amount_usd} [Symbol]/USDT')
    print(f'3) Any further drop of more than {min_additional_drop}% (relative to prev buy) will also be bought')
    print('')


@app.command()
def main(freq: int = config["General"]["frequency"], 
                    amount_usd = config['General']['order_amount_usd'], 
                    min_drop: float = config['General']['min_initial_drop'], 
                    min_additional_drop: float = config['General']['min_additional_drop'], 
                    dry_run: bool = config['General']['dry_run'],
                    ):
    
    bot_token = config['IM']['telegram_bot_token']
    chat_id = config['IM']['telegram_chat_id']
    retry_after = config['General']['retry_after']
    
    print_header(freq, amount_usd, min_drop, min_additional_drop, dry_run)
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
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if biggest_drop is None:
            print(f'{now} - None of the symbols dropping. Checking again in {freq} minutes...')
            time.sleep(freq * 60)
            continue

        if biggest_drop['24h_pct_chg'] < -min_drop:
            previous_order = orders.get(biggest_drop['symbol'])
            
            if biggest_drop is not None and crypto.is_better_than_previous(biggest_drop, previous_order, min_drop):
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
            print(f'{now} - No big discounts. Checking again in {freq} minutes...')

        # time.sleep(freq * 30)
        time.sleep(freq * 60)


if __name__ == '__main__':
    typer.run(main)
