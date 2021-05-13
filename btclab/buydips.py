import time
import ccxt
import typer
import logging
from typing import List
import crypto
import utils
import db
from datetime import datetime, timedelta
from ccxt.base.errors import InsufficientFunds, BadSymbol


config = utils.get_config()

def print_header(symbols, freq,  amount_usd, min_drop, min_additional_drop, dry_run):
    title = 'Crypto prices monitor running. Hit q to quit'
    print(f'\n{"-" * len(title)}\n{title}\n{"-" * len(title)}')
    if dry_run:
        print('Running in summulation mode\n')
    
    print(f'1) Tracking price changes in: {" ".join(symbols)} every {freq} minutes')
    print(f'2) Any drop of {min_drop}% or more will trigger a buy order of {amount_usd} [Symbol]/USDT')
    print(f'3) Any further drop of more than {min_additional_drop}% (relative to prev buy) will also be bought')
    print()


def bought_less_than_24h_ago(symbol:str, orders: dict) -> bool:
    if symbol in orders:
        now = datetime.now()
        bought_on = datetime.fromtimestamp(orders[symbol]['timestamp']/1000)
        diff = now - bought_on
        return diff.days <= 1
    return False


def main(
        symbols: List[str] = typer.Argument(None, 
            help='The symbols you want to buy if they dip enough. e.g: BTC/USDT, ETH/USDC', show_default=False),
        amount_usd: float = typer.Option(config['General']['order_amount_usd'], '--amount-usd', 
            help='Amount to buy of symbol in base currency'), 
        freq: int = typer.Option(config['General']['frequency'], 
            help='Frequency in minutes to check for new price drops'),
        min_drop: float = typer.Option(config['General']['min_initial_drop'],
            help='Min drop in percentage in the last 24 hours for placing a buy order'),
        min_additional_drop: float = typer.Option(config['General']['min_additional_drop'], 
            help='The min additional drop in percentage to buy a symbol previoulsy boght'),
        dry_run: bool = typer.Option(config['General']['dry_run'], 
            help='Run in simmulation mode. Don\'t buy anything'),
        reset_cache: bool = typer.Option(False)):

    """
    Example usage:
    python buydips BTC/USDT ETH/USDT DOT/USDT --freq 10 --min-drop 7 --min-aditional-drop 2

    Start checking prices of BTC/USDT ETH/USDT and DOT/USDT every 10 minutes
    Buy the one with the biggest drop in the last 24h if that drop is bigger than 7% 
    If the biggest drop is in a symbol previouly bought, buy again only if it is down 2% from last buy price
    """

    bot_token = config['IM']['telegram_bot_token']
    chat_id = config['IM']['telegram_chat_id']
    
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

    non_supported_symbols = crypto.get_unsupported_symbols(binance, symbols)
    if len(non_supported_symbols) > 0:
        typer.echo(f'Sorry, {", ".join(non_supported_symbols)}\n')
        raise typer.Exit(code=-1)

    orders = {} if reset_cache else db.get_orders() 

    while True:
        tickers = binance.fetch_tickers(symbols)
        
        for symbol, ticker in tickers.items():
            now = datetime.now()
            now_str = now.strftime('%Y-%m-%d %H:%M:%S')
            buy_first_time = False
            buy_again = False
            if symbol in orders and bought_less_than_24h_ago(symbol, orders):
                discount_pct = (ticker['ask'] / orders[symbol]['price'] - 1) * 100
                buy_again = discount_pct < -min_additional_drop
            else:
                buy_first_time = ticker['percentage'] < -min_drop
            
            if buy_first_time or buy_again:
                try:
                    order = crypto.place_order(exchange=binance, 
                                                symbol=symbol, 
                                                price=ticker['last'], 
                                                amount_in_usd=amount_usd,
                                                dry_run=dry_run)
                except InsufficientFunds:
                    msg = f'Insufficient funds. Trying again in {freq} minutes...'
                else:
                    orders[symbol] = order
                    msg = crypto.short_summary(order, ticker['percentage'])
                    db.save(orders)
                
                print(f'{now_str} - {msg}')
                utils.send_msg(bot_token, chat_id, msg)

        print(f'\n{now_str} - Checking again in {freq} minutes...')
        time.sleep(freq * 60)
        msg = ''


if __name__ == '__main__':
    logging.basicConfig()
    typer.run(main)