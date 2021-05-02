import time
import ccxt
import typer
import logging
from typing import List
import btclab.crypto as crypto
import btclab.utils as utils
from datetime import datetime
from ccxt.base.errors import InsufficientFunds, BadSymbol


config = utils.get_config()

def print_header(symbols, freq,  amount_usd, min_drop, min_additional_drop, dry_run):
    title = 'Crypto prices monitor running'
    print(f'\n{"-" * len(title)}\n{title}\n{"-" * len(title)}')
    if dry_run:
        print('Running in summulation mode\n')
    
    print(f'1) Tracking price changes in: {" ".join(symbols)} every {freq} minutes')
    print(f'2) Any drop of {min_drop}% or more will trigger a buy order of {amount_usd} [Symbol]/USDT')
    print(f'3) Any further drop of more than {min_additional_drop}% (relative to prev buy) will also be bought')
    print('')


def main(
        symbols: List[str] = typer.Argument(None, 
            help='Tickers to check for dipzs. e.g: BTC/USDT, ETH/USDC', show_default=False),
        amount_usd: float = typer.Option(config['General']['order_amount_usd'], '--amount-usd', 
            help='Amount to buy of symbol in base currency'), 
        freq: int = typer.Option(config["General"]["frequency"],
            help='Frequency in minutes to check for new price drops'),
        min_drop: float = typer.Option(config['General']['min_initial_drop'],
            help='Min drop in percentage in the last 24 hours for placing a buy order'),
        min_additional_drop: float = typer.Option(config['General']['min_additional_drop'], 
            help='The min additional drop in percentage to buy a symbol previoulsy boght'),
        dry_run: bool = typer.Option(config['General']['dry_run'], 
            help='Run in simmulation mode. Don\'t buy anything')):

    """
    buydips BTC/USDT ETH/USDT DOT/USDT --freq 10 --min-drop 7 --min-aditional-drop 2

    Start checking prices of BTC/USDT ETH/USDT and DOT/USDT every 10 minutes
    Buy the one with the biggest drop in the last 24h if that drop is bigger than 7% 
    If the biggest drop is in a symbol previouly bought, buy again only if it is down 2% from last buy price
    """

    # TODO Check if symbols are supported by the exchange

    bot_token = config['IM']['telegram_bot_token']
    chat_id = config['IM']['telegram_chat_id']
    retry_after = config['General']['retry_after']
    
    if not symbols:
        symbols = config['General']['tickers']

    print_header(symbols, freq, amount_usd, min_drop, min_additional_drop, dry_run)
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
        biggest_drop = None
        try:
            biggest_drop = crypto.get_biggest_drop(binance, symbols)
        except BadSymbol as bs:
            typer.echo(f'Sorry, {str(bs)}\n')
            raise typer.Exit(code=-1)

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
                    utils.send_msg(bot_token, chat_id)
                    continue
                else:
                    msg = crypto.short_summary(order, biggest_drop['24h_pct_chg'])
                    utils.send_msg(bot_token, chat_id, msg)
                    print(f'\n{now} - {msg}')
                    orders[biggest_drop['symbol']] = order
                    # save(orders)
        else:
            print(f'{now} - Nothing dropping {min_drop}% or more. Checking again in {freq} minutes...')

        # time.sleep(freq * 30)
        time.sleep(freq * 60)


if __name__ == '__main__':
    logging.basicConfig()
    typer.run(main)