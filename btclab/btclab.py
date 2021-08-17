import os
import time
import logging
import ccxt
import typer
import logging
import crypto
import utils
import yaml
import dca as dca_lib
import db
import dips
from enum import Enum
from datetime import datetime
from logconf import logger
from retry.api import retry
from ccxt.base.errors import InsufficientFunds, NetworkError, RequestTimeout


class Strategy(Enum):
    BUY_THE_DIPS = 'dip'
    DCA = 'dca'


def get_config():
    """Returns a dictionary with the info in config.yaml"""
    with open('./btclab/config.yaml', 'r') as stream:
        try:
            config = yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            print(exc)
    return config


config = get_config()
def complete_config(verbose: bool = typer.Option(config['General']['reset'], '--verbose', '-v',
                        help='Show detailed info'),
                    reset: bool = typer.Option(config['General']['reset'], '--reset', '-r',
                        help='Reset previous orders info'),
                    silent: bool = typer.Option(False, '--silent', '-s', 
                        help='Silent mode. Do not send notifications to chat'),
                    dry_run: bool = typer.Option(config['General']['dry_run'], 
                        help='Run in simmulation mode. Don\'t buy anything')):
    """
    A Binance CLI tool for DCA and dip buying
    """

    global config
    config['General']['reset'] = reset
    config['General']['dry_run'] = dry_run
    config['General']['verbose'] = verbose
    config['General']['silent'] = silent

    if verbose:
        logger.setLevel(logging.DEBUG)

    if os.environ.get('TELEGRAM_BOT_TOKEN') is not None: # Prefer the value in the environment variable
        config['IM']['telegram_bot_token'] = os.environ.get('TELEGRAM_BOT_TOKEN').strip()
    
    if config['IM']['telegram_bot_token'] == '':
        msg = 'Set the Telegram bot token in the TELEGRAM_BOT_TOKEN environment variable or in the config.yaml file'
        logging.error(msg)
        raise typer.Exit(code=-1)

    chat_id = str(config['IM']['telegram_chat_id'])
    if chat_id.strip() == '':
        logging.error('Set the Telegram chat id in the config.yaml file')
        raise typer.Exit(code=-1)

    if os.environ.get('BINANCE_API_KEY') is not None:
        config['Exchange']['api_key'] = os.environ.get('BINANCE_API_KEY')

    while config['Exchange']['api_key'] is None or config['Exchange']['api_key'].strip() == '':
        config['Exchange']['api_key'] = typer.prompt('Enter your Binance API key:').strip()
    
    if os.environ.get('BINANCE_API_SECRET') is not None:
        config['Exchange']['api_secret'] = os.environ.get('BINANCE_API_SECRET')

    while config['Exchange']['api_secret'] is None or config['Exchange']['api_secret'].strip() == '':
        config['Exchange']['api_secret'] = typer.prompt('Enter your Binance API secret:').strip()

    global exchange
    exchange = ccxt.binance(
        {
            'apiKey': config['Exchange']['api_key'], 
            'secret': config['Exchange']['api_secret'], 
            'enableRateLimit': True 
        }
    )


exchange = None
app = typer.Typer(callback=complete_config)


def symbols_callback(symbols: list[str]):
    if not symbols: # If a a list of symbols was not passed as param
        symbols = [s.upper() for s in config['General']['symbols']]
    
    if len(symbols) == 0:
        logging.error('Pass a symbol or list of symbols as parameters or include them in config.yaml file')
        raise typer.Exit(code=-1)
    
    # Check if symbols are supported by the exchange
    non_supported_symbols = crypto.get_non_supported_symbols(exchange, symbols)
    if len(non_supported_symbols) > 0:
        msg = (f'The following symbol(s) are not supported in {exchange.name}: '
                f'{", ".join(non_supported_symbols)}. Execution stoped\n')
        raise typer.BadParameter(msg)

    return symbols
    

@app.command()
@retry((RequestTimeout, NetworkError), delay=15, jitter=5, logger=logger)
def buydips(
        symbols: list[str] = typer.Argument(None, callback=symbols_callback,
            help='The symbols you want to buy. e.g. BTC/USDT ETH/USDT ', show_default=False),
        order_cost: float = typer.Option(config['General']['order_cost'], '--cost', '-c', 
            help='Amount of quote currency to buy of each symbol'), 
        increase_cost_by: float = typer.Option(config['General']['increase_cost_by'], '--increase-cost-by', '-i', 
            help='The increase in the amount to buy when a symbol was already bought in the last 24 hours'), 
        frequency: float = typer.Option(config['General']['frequency'], '--frequency', '-f',
            help='Frequency in minutes to check for new price drops'),
        min_drop: str = typer.Option(config['General']['min_drop'], '--min-drop', '-m', 
            help='Min drop in the last 24h (in standard deviations, ex. 2SD, or in %) for placing a buy order'),
        min_next_drop: float = typer.Option(config['General']['min_next_drop'], '--min-next-drop', '-n',
            help='The min additional drop in percentage to buy a symbol previoulsy bought')):
    
    """
    Example usage:
    python buydips.py BTC/USDT ETH/USDT DOT/USDT --freq 10 --min-drop 2SD --min-aditional-drop 2

    Start checking prices of BTC/USDT ETH/USDT and DOT/USDT every 10 minutes
    Buy the ones with a drop in the last 24h greater than two standard deviations (2SD)
    If a symbols was previouly bought, buy again only if it is down 2% from last buy price
    """
    dry_run = config['General']['dry_run']
    orders = db.get_orders(Strategy.BUY_THE_DIPS, dry_run)
    
    # Get min drop in % for each symbol
    min_drops = dips.get_min_drops_in_pct(symbols, min_drop, exchange)

    header = dips.get_buydips_header(config, symbols, min_drops, orders)
    print (header)

    while True:
        for symbol in symbols:
            ticker = exchange.fetch_ticker(symbol)
            min_drop_pct = min_drops[symbol] # Get min drop in percentage if min_drop is given in std dev
            
            try:
                order = dips.buy_initial_drop(exchange, ticker, order_cost, min_drop_pct, orders, config)
                if order is None:
                    order = dips.buy_additional_drop(exchange, ticker, orders, config)
            except InsufficientFunds:
                retry_after = config['General']['retry_after']
                msg = f'Insufficient funds. Trying again in {retry_after} minutes...'
                logger.warning(msg)
                utils.send_msg(config['IM']['telegram_bot_token'], config['IM']['telegram_chat_id'], msg)
                time.sleep(retry_after * 60)
                break
            else:
                if order is not None:
                    orders[symbol] = order
                    db.save(orders, Strategy.BUY_THE_DIPS, dry_run)

        logger.debug(f'Checking again for price drops in {frequency} minutes...')
        time.sleep(frequency * 60)


@app.command()
@retry(NetworkError, delay=15, jitter=5, logger=logger)
def dca(symbols: list[str] = typer.Argument(None, help='The symbols you want to buy (e.g: BTC/USDT ETH/USDC)'),
        frequency: float = typer.Option(..., '--frequency', '-f',
            help='In days. Buys will occur with this frequency'),
        cost: float = typer.Option(None, '--cost', '-c',
            help='The amount in quote currency for each buy')):

    """DCA is a long-term strategy, where an investor regularly buys small amounts of an asset 
    over a period of time, no matter the price. This application allows you to do that.
    """

    dry_run = config['General']['dry_run']
    orders = db.get_orders(Strategy.DCA, dry_run) 
    header = dca_lib.get_dca_header(config, symbols, orders, frequency)
    print(header)
    times_ran = 0

    while True:
        if config['General']['reset'] and times_ran == 0:
            orders = {} 
        else:
            orders = db.get_orders(Strategy.DCA, dry_run)
        
        for symbol in symbols:
            if dca_lib.time_to_buy(symbol, orders, frequency):
                order = crypto.place_buy_order(exchange, symbol, None, cost, 'market', dry_run)
                orders[symbol] = order
                db.save(orders, Strategy.DCA, dry_run)
                real_cost = order['cost']
                price = order['average']
                
                msg = dca_lib.get_dca_buy_msg(real_cost, symbol, price, frequency, dry_run)
                logger.info(msg)
                utils.send_msg(config['IM']['telegram_bot_token'], config['IM']['telegram_chat_id'], msg)

            # Early alert for next buy
            insufficient_balance = crypto.insufficient_funds(exchange, symbol, cost)
            if insufficient_balance:
                retry_after = config['General']['retry_after']
                msg = crypto.get_insufficient_funds_msg(symbol, cost, insufficient_balance, retry_after)
                logger.warning(msg)
                utils.send_msg(config['IM']['telegram_bot_token'], config['IM']['telegram_chat_id'], msg)
                time.sleep(retry_after * 60)
                break
            
        times_ran += 1
        time.sleep(frequency * 60)


if __name__ == '__main__':
    app()
