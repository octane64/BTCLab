import os
import time
import yaml
import logging
import ccxt
import typer
import logging
import crypto
import utils
import data
import db
from crypto import Strategy
from datetime import datetime
from logconf import logger
from retry.api import retry
from ccxt.base.errors import InsufficientFunds, NetworkError, RequestTimeout


def get_config():
    # Load initial config params from config.yaml
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

    config['General']['reset'] = reset
    config['General']['dry_run'] = dry_run
    config['General']['verbose'] = verbose
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


def print_buydips_header(symbols, amount, increase_amount_by, freq, min_drop, min_next_drop, min_drop_pct, orders, dry_run):
    title = 'BTCLab crypto engine running for dip buying strategy'
    print(f'\n{"-" * len(title)}\n{title}\n{"-" * len(title)}')
    print(f'\n- Tracking price drops in: {", ".join(symbols)}')
    
    msg_min_drop = std_devs_as_pct_str(min_drop, symbols, min_drop_pct)

    if config['General']['dry_run']:
        print('- Running in simmulation mode, balances will not be affected')
    print(f'- First order will be placed if prices drop at least {msg_min_drop} from last 24 hours')
    print(f'- Additional orders will be placed on drops of {min_next_drop}% from last purchase price')
    print(f'- The amount to buy on each order will be {amount} of quote currency')
    
    if increase_amount_by > 0:
        print(f'- That amount will increase by {increase_amount_by} for previoulsy bought symbols with additional drops')

    if len(orders) > 0:
        print('\n\nYou previously bought on price dips:')
        for key, value in orders.items():
            # In case order timestamp is in milliseconds, convert to seconds
            timestamp = value['timestamp']
            if timestamp - int(timestamp) == 0:
                timestamp /= 1000
            strdate = datetime.fromtimestamp(timestamp).strftime('%x %X')
            print(f'- {key} -> {value["amount"]:.6g} @ {value["price"]:,.2f} on {strdate}')
    print()

def std_devs_as_pct_str(min_drop: str, symbols: list[str], min_drop_pct: list[float]):
    if 'sd' in min_drop.lower().strip():
        msg_min_drop = min_drop.upper().replace('SD', ' Std dev (')
        if len(symbols) > 1:
            for s in symbols:
                msg_min_drop += f'{s}: {min_drop_pct[s]:.2f}%, '
            msg_min_drop = msg_min_drop[:-2] + ')'
        else:
            msg_min_drop += f'{min_drop_pct[symbols[0]]:.2f}%)'
        
    else:
        msg_min_drop = min_drop + '%'
    return msg_min_drop


def get_min_drops_in_pct(symbols, min_drop: str, binance) -> dict:
    """Returns a dict with the minimum drop for each symbol as a percentage (float)
    The input min_drop is a string that can either be a number of standar deviations 
    (ex. 1SD, 1.SD) or a percentage in the form of a numeric value with or without a 
    percentage sign (ex. 8.5 or 8.5%)
    """

    min_drop_pcts = {}
    std_devs = data.get_std_dev(binance, symbols)
    min_drop = min_drop.replace('%', '').replace(' ', '')
    if 'sd' in min_drop.lower():
        num_of_sd = float(min_drop.lower().replace('sd', '').replace(' ', ''))
        # for symbol in symbols:
            # min_drop_pcts[symbol] = num_of_sd * std_devs[symbol] * 100
        min_drop_pcts = {symbol: num_of_sd * std_devs[symbol] * 100 for symbol in symbols}
    else:
        min_drop_pcts = {symbol: float(min_drop) for symbol in symbols}
    
    return min_drop_pcts


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


def buy_initial_drop(ticker, orders, min_drop_pct, cost):
    """
    Places a new buy order if symbol hasn't been bought and last 24h drop surpasses the min_drop_pct limit
    """
    symbol = ticker['symbol']
    if symbol not in orders and ticker['percentage'] < -min_drop_pct:
        asset = symbol.split('/')[0]
        quote_ccy = symbol.split('/')[1]
        price = ticker['last']
        order = crypto.place_buy_order(exchange, symbol, price, cost, 'market', config['General']['dry_run'])
        if order: 
            cost = order['cost']
        
        msg = (f'Buying {cost:,.2f} {quote_ccy} of {asset} @ {price:,.2f}. '
               f'Drop in last 24h is {ticker["percentage"]:.2f}%')
        if config['General']['dry_run']:
            msg += '. (Running in simulation mode, balance was not affected)'
        
        logger.debug(msg)
        utils.send_msg(config['IM']['telegram_bot_token'], config['IM']['telegram_chat_id'], msg)
        return order
    
    return None


def buy_additional_drop(ticker, orders, min_next_drop, increase_cost_by):
    """
    Places a new buy order if symbol has been bought recently and last 24h drop surpasses the min_next_drop limit
    """
    symbol = ticker['symbol']
    if crypto.bought_within_the_last(24, symbol, orders):
        drop_from_last_order = (ticker['ask'] / orders[symbol]['price'] - 1) * 100
        
        if drop_from_last_order < -min_next_drop:
            asset = symbol.split('/')[0]
            quote_ccy = symbol.split('/')[1]
            price = ticker['ask']

            cost_of_previous_order = orders[symbol]['cost']
            cost = cost_of_previous_order + increase_cost_by
            # if increase_cost_by > 0:
            #     cost += increase_cost_by

            order = crypto.place_buy_order(exchange, symbol, price, cost, config['General']['dry_run'])
            if order:
                cost = order['cost']
            msg = (f'Buying {cost:,.2f} {quote_ccy} of {asset} @ {price:,.2f}. '
                    f'Current price is {drop_from_last_order:.2f}% from the previous buy order')
            if config['General']['dry_run']:
                msg += '. (Running in simulation mode, balance was not affected)'
            
            logger.debug(msg)
            utils.send_msg(config['IM']['telegram_bot_token'], config['IM']['telegram_chat_id'], msg)
            return order
    return None
    

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
    
    orders = db.get_orders(Strategy.BUY_THE_DIPS)
    
    # Get min drop in % for each symbol
    min_drops = get_min_drops_in_pct(symbols, min_drop, exchange)

    print_buydips_header(symbols, order_cost, increase_cost_by, frequency, min_drop,
                            min_next_drop, min_drops, orders, config['General']['reset'])
    
    while True:
        for symbol in symbols:
            ticker = exchange.fetch_ticker(symbol)
            min_drop_pct = min_drops[symbol] # Get min drop in percentage if min_drop is given in std dev
            
            try:
                order = buy_initial_drop(ticker, orders, min_drop_pct, order_cost)
                if order is None:
                    order = buy_additional_drop(ticker, orders, min_next_drop, increase_cost_by)
                
                if order is not None:
                    orders[symbol] = order
                    db.save(orders, Strategy.BUY_THE_DIPS)
            except InsufficientFunds:
                retry_after = config['General']['retry_after']
                msg = (
                    f'Insufficient funds. Trying again in {retry_after} minutes...'
                )
                logger.warning(msg)
                utils.send_msg(config['IM']['telegram_bot_token'], config['IM']['telegram_chat_id'], msg)
                time.sleep(retry_after * 60)
                break

        logger.debug(f'Checking again for price drops in {frequency} minutes...')
        time.sleep(frequency * 60)


def days_from_last_dca(symbol, orders):
    """
    Returns the number of days that have passed since the last dca order 
    was placed or -1 if never been placed
    """
    if symbol not in orders:
        return -1 # Arbitrary long number meaning too many days / never buoght
    else:
        last_dca_order = orders[symbol]
        timestamp = last_dca_order['timestamp']
        
        # In case order timestamp is in milliseconds, convert to seconds
        if timestamp - int(timestamp) == 0:
            timestamp /= 1000
        
        diff = datetime.now() - datetime.fromtimestamp(timestamp)
        return diff.days


def print_dca_header(symbols, orders, freq):
    title = 'BTCLab crypto engine running for DCA strategy...'
    
    print(f'\n{"-" * len(title)}\n{title}\n{"-" * len(title)}')
    if config['General']['dry_run']:
        print('- Running in simmulation mode, balances will not be affected')
    print(f'\nOrders to buy {", ".join(symbols)} will be placed every {freq} days... Hit Ctrl + C to stop')
    
    if len(orders) > 0:
        print('\n\nYou previously bought:')
        for key, value in orders.items():
            timestamp = value['timestamp'] / 1000
            strdate = datetime.fromtimestamp(timestamp).strftime('%x %X')
            print(f'- {key} -> {value["amount"]:.6g} @ {value["price"]:,.2f} on {strdate}')
    
    typer.echo()


def insufficient_funds(symbol, order_cost):
    """Returns the balance in quote currency of symbol if insufficient to cover order cost, zero otherwise
    """
    quote_ccy = symbol.split('/')[1]
    balance = crypto.get_balance(exchange, quote_ccy)
    
    if balance < order_cost:
        return balance
    return 0


def get_insufficient_funds_msg(symbol, order_cost, balance):
    asset = symbol.split('/')[0]
    quote_ccy = symbol.split('/')[1]
    retry_after = config['General']['retry_after']
    msg = (
        f'Insufficient funds. Next order will try to buy {order_cost:,.0f} {quote_ccy} '
        f'of {asset} but {quote_ccy} balance is {balance:,.2f}. Trying again in '
        f'{retry_after} minutes...'
    )
    return msg


@app.command()
def dca(symbols: list[str] = typer.Argument(..., help='The symbols you want to buy (e.g: BTC/USDT ETH/USDC)'),
        frequency: float = typer.Option(..., help='In days. Buys will occur with this frequency'),
        cost: float = typer.Option(..., help='The amount in quote currency for each buy')):

    """DCA is a long-term strategy, where an investor regularly buys small amounts of an asset 
    over a period of time, no matter the price. This application allows you to do that.
    """

    orders = db.get_orders(Strategy.DCA)
    print_dca_header(symbols, orders, frequency)
    # TODO Save to another file when in simulation mode
    dry_run = config['General']['dry_run']
    times_ran = 0

    while True:
        if config['General']['reset'] and times_ran == 0:
            orders = {} 
        else:
            orders = db.get_orders(Strategy.DCA)
        
        for symbol in symbols:
            if time_to_buy(symbol, orders, frequency):
                order = crypto.place_buy_order(exchange, symbol, None, cost, 'market', dry_run)
                update_orders(order, orders, symbol)
                real_cost = order['cost'] # FIX Dont overwrite original cost
                price = order['average']
                
                msg = get_dca_buy_msg(real_cost, symbol, price, frequency, dry_run)
                logger.info(msg)
                utils.send_msg(config['IM']['telegram_bot_token'], config['IM']['telegram_chat_id'], msg)

            # Early alert for next buy
            insufficient_balance = insufficient_funds(symbol, cost)
            if insufficient_balance:
                retry_after = config['General']['retry_after']
                msg = get_insufficient_funds_msg(symbol, cost, insufficient_balance)
                logger.warning(msg)
                utils.send_msg(config['IM']['telegram_bot_token'], config['IM']['telegram_chat_id'], msg)
                time.sleep(retry_after * 60)
                break
            
        times_ran += 1
        time.sleep(frequency * 60)


def get_dca_buy_msg(real_cost, symbol, price, frequency, dry_run):
    msg = f'Buying {real_cost:.2f} of {symbol} @ {price:,.5g} today'
    msg += f'. Next buy will ocurr in {frequency} days'
    if dry_run:
        msg += '. (Running in simulation mode, balance was not affected)'
    return msg


def update_orders(order, orders, symbol):
    if order:
        orders[symbol] = order
        db.save(orders, Strategy.DCA)


def time_to_buy(symbol, previous_orders, dca_freq):
    """
    Returns true if today is a day to buy in a 
    dollar-cost-average (dca) plan, false otherwise
    """
    
    days_since_last_dca = days_from_last_dca(symbol, previous_orders)
    if days_since_last_dca == -1 or days_since_last_dca >= dca_freq:
        return True
    return False


if __name__ == '__main__':
    app()
