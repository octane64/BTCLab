import os
import time
import yaml
import logging
import ccxt
import typer
import dataclasses
import logging
import crypto
import utils
import data
import db
from datetime import date, datetime
from logconf import logger
from retry.api import retry
from ccxt.base.errors import NetworkError, RequestTimeout


def get_config():
    # Load initial config params from config.yaml
    with open('./btclab/config.yaml', 'r') as stream:
        try:
            config = yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            print(exc)
    return config

config = get_config()


def short_summary(order, pct_chg) -> str:
    """
    Returns a brief description of an order
    order param is a dict with the structure defined in
    https://github.com/ccxt/ccxt/wiki/Manual#order-structure
    """
    action = "Buying" if order["side"] == "buy" else "Sold"

    # Ex: Buying 0.034534 BTC/USDT @ 56,034.34
    msg = (
        f'{order["symbol"]} is down {pct_chg:.2f}% from the last 24 '
        f'hours: {action} {order["amount"]:.6f} @ {order["price"]:,.2f}'
    )
    return msg


def is_better_than_previous(new_order, previous_order, min_discount) -> bool:
    """Returns True if price in new_order is better (min_discount cheaper) 
    than the price in previous_order, False otherwise
    """
    assert min_discount > 0, 'min_discount should be a positive number'
    
    discount = new_order['price'] / previous_order['price'] - 1
    return discount < 0 and abs(discount) > min_discount/100


def print_header(symbols, amount, increase_amount_by, freq, min_drop, min_next_drop, min_drop_pct, orders, dry_run):
    title = 'Crypto prices monitor running'
    print(f'\n{"-" * len(title)}\n{title}\n{"-" * len(title)}')
    
    start_msg = 'Starting new session'
    if dry_run:
        start_msg += ' (Running in simmulation mode)'
    print()
    print(start_msg)

    print(f'- Tracking price drops in: {", ".join(symbols)}')
    
    msg_min_drop = std_devs_as_pct_str(min_drop, symbols, min_drop_pct)

    print(f'- First order will be placed if prices drop at least {msg_min_drop} from last 24 hours')
    print(f'- Additional orders will be placed on drops of {min_next_drop}% from first order price')
    print(f'- The amount to buy on each order will be {amount} of quote currency')
    
    if increase_amount_by > 0:
        print(f'- Amount will increase by {increase_amount_by} of quote currency for previoulsy bought symbols')
    print('- Run with --verbose option to see more detail')
    print('- Run with --help to see all options\n')

    if len(orders['Non-DCA']) > 0:
        print('You previously bought on price dips:')
        for key, value in orders['Non-DCA'].items():
            strdate = datetime.fromtimestamp(value["timestamp"]).strftime('%x %X')
            print(f'- {key} -> {value["amount"]:.5f} @ {value["price"]:,.2f} on {strdate}')

    print()
    if len(orders['DCA']) > 0:
        print('You previously bought on periodic buys:')
        for key, value in orders['DCA'].items():
            strdate = datetime.fromtimestamp(value["timestamp"]).strftime('%x %X')
            print(f'- {key} -> {value["amount"]:.5f} @ {value["price"]:,.2f} on {strdate}')

    print(f'\nChecking for new price drops every {freq} minutes... Hit Ctrl + C to exit')
    typer.echo()


def std_devs_as_pct_str(min_drop: str, symbols: list[str], min_drop_pct: list[float]):
    if 'sd' in min_drop.lower().strip():
        msg_min_drop = min_drop.upper().replace('SD', ' Std dev (')
        for s in symbols:
            msg_min_drop += f'{s}: {min_drop_pct[s]:.2f}%, '
        msg_min_drop = msg_min_drop[:-2] + ')'
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


def get_next_order_quote_ccy_amount(symbol: str, orders: dict, base_amount: float, 
                                            increase_amount_by: float) -> float:
    """Returns the amount in quote currency for the next order of a given symbol
    """
    if symbol not in orders or increase_amount_by == 0:
        return base_amount

    prev_amount = orders['Non-DCA'][symbol]['price'] * orders['Non-DCA'][symbol]['amount']
    return prev_amount + increase_amount_by


def check_symbols(binance, symbols):
    # Check if symbols are supported by the exchange
    non_supported_symbols = crypto.get_non_supported_symbols(binance, symbols)
    if len(non_supported_symbols) > 0:
        logging.error((f'The following symbol(s) are not supported in {binance.name}: '
                            f'{", ".join(non_supported_symbols)}. Execution stoped\n'))
        raise typer.Exit(code=-1)


@retry((RequestTimeout, NetworkError), delay=15, jitter=5, logger=logger)
def main(
        symbols: list[str] = typer.Argument(None, 
            help='The symbols you want to buy, separated by spaces. Either use pairs like '\
                'BTC/USDT ETH/USDT or main symbols without a quote currency. e.g: BTC ETH', show_default=False),
        quote_currency: str = typer.Option('USDT', help='Quote currency to use when missing in symbols list'),
        quote_ccy_amount: float = typer.Option(config['General']['quote_ccy_amount'], '--amount-usd', '-a', 
            help='Amount of quote currency to buy of each symbol'), 
        increase_amount_by: float = typer.Option(config['General']['increase_amount_by'], '--increase-amount-by', '-i', 
            help='The increase in the amount to buy when a symbol was already bought in the last 24 hours'), 
        freq: float = typer.Option(config['General']['frequency'], '--freq', '-f',
            help='Frequency in minutes to check for new price drops'),
        min_drop: str = typer.Option(config['General']['min_drop'], '--min-drop', '-m', 
            help='Min drop in the last 24h (in standard deviations, ex. 2SD, or in %) for placing a buy order'),
        min_next_drop: float = typer.Option(config['General']['min_next_drop'], '--min-next-drop', '-n',
            help='The min additional drop in percentage to buy a symbol previoulsy bought'),
        dry_run: bool = typer.Option(config['General']['dry_run'], 
            help='Run in simmulation mode. Don\'t buy anything'),
        dca_amount: float = typer.Option(config['General']['dca_amount'], '--dca-amount', 
            help='Amount to buy periodically to dollar cost average or DCA'),
        dca_freq: int = typer.Option(config['General']['dca_freq'], '--dca-freq', 
            help='Days to wait between DCA buys'),
        reset_cache: bool = typer.Option(False, '--reset-cache', '-r', help='Reset info of previous operations'),
        silent: bool = typer.Option(False, '--silent', '-s', help='Silent mode. Do not send notifications to chat'),
        verbose: bool = typer.Option(False, '--verbose', '-v', help='Verbose mode')):
    
    """
    Example usage:
    python buydips.py BTC ETH DOT --freq 10 --min-drop 2SD --min-aditional-drop 2

    Start checking prices of BTC/USDT ETH/USDT and DOT/USDT every 10 minutes
    Buy the ones with a drop in the last 24h greater than two standard deviations (2SD)
    If a symbols was previouly bought, buy again only if it is down 2% from last buy price
    """
    if os.environ.get('TELEGRAM_BOT_TOKEN') is not None: # Prefer the value in the environment variable
        bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    else:
        bot_token = config['IM']['telegram_bot_token'].strip()
    
    if bot_token.strip() == '':
        logging.error('Set the Telegram bot token in the TELEGRAM_BOT_TOKEN environment variable or in the config.yaml file')
        raise typer.Exit(code=-1)

    chat_id = str(config['IM']['telegram_chat_id'])
    if chat_id.strip() == '':
        logging.error('Set the Telegram chat id in the config.yaml file')
        raise typer.Exit(code=-1)
    
    if not symbols: # If a a list of symbols was not passed as param
        symbols = config['General']['tickers']
    
    if len(symbols) == 0:
        logging.error('Pass a symbol or list of symbols as parameters or include them in config.yaml file')
        raise typer.Exit(code=-1)
    else:
        # symbols = [s.upper() for s in symbols]
        symbols = [f'{s.upper()}/{quote_currency.upper()}' if '/' not in s else s.upper() for s in symbols]

    if os.environ.get('BINANCE_API_KEY') is not None:
        config['Exchange']['api_key'] = os.environ.get('BINANCE_API_KEY')

    while config['Exchange']['api_key'] is None or config['Exchange']['api_key'].strip() == '':
        config['Exchange']['api_key'] = typer.prompt('Enter your Binance API key:').strip()
    
    if os.environ.get('BINANCE_API_SECRET') is not None:
        config['Exchange']['api_secret'] = os.environ.get('BINANCE_API_SECRET')

    while config['Exchange']['api_secret'] is None or config['Exchange']['api_secret'].strip() == '':
        config['Exchange']['api_secret'] = typer.prompt('Enter your Binance API secret:').strip()

    if verbose:
        logger.setLevel(logging.DEBUG)

    binance = ccxt.binance(
        {
            'apiKey': config['Exchange']['api_key'],
            'secret': config['Exchange']['api_secret'],
            'enableRateLimit': True,
        }
    )

    # Check if symbols are supported by the exchange
    check_symbols(binance, symbols)

    # Load previous orders
    orders = db.get_orders() if not reset_cache else {'DCA': {}, 'Non-DCA': {}}
    
    # Get min drop in % for each symbol
    min_drops_pct = get_min_drops_in_pct(symbols, min_drop, binance)

    print_header(symbols, quote_ccy_amount, increase_amount_by, freq, min_drop,
                    min_next_drop, min_drops_pct, orders, dry_run)

    while True:
        now = datetime.now().strftime('%m/%d/%Y, %H:%M:%S')
        if not verbose:
            print(f'Last check: {now} - Hit Ctrl + C to exit', end='\r')
        
        for symbol in symbols:
            ticker = binance.fetch_ticker(symbol)
            quote_ccy = symbol.split('/')[1]
            asset = symbol.split('/')[0]
            balance = crypto.get_balance(binance, quote_ccy)
            recently_bought = False
            buy_first_time = False
            buy_again = False

            if dca_amount > 0:
                if balance > dca_amount:
                    dca(dca_amount, symbol, orders, dca_freq, binance, ticker, dry_run, silent, bot_token)
                    balance = crypto.get_balance(binance, quote_ccy)
                else:
                    msg = f'Insufficient funds for DCA. Attempting to buy {quote_ccy} {dca_amount:.2f} of {asset} but only {quote_ccy} {balance:.2f} available.'
                    logger.warning(msg)
                    if not silent:
                        utils.send_msg(bot_token, config['IM']['telegram_chat_id'], msg)

            if symbol in orders['Non-DCA'] and crypto.bought_less_than_24h_ago(symbol, orders, dry_run):
                amount = get_next_order_quote_ccy_amount(symbol, orders['Non-DCA'], quote_ccy_amount, increase_amount_by)
                discount_pct = (ticker['last'] / orders['Non-DCA'][symbol]['price'] - 1) * 100
                recently_bought = True
                buy_again = discount_pct < -min_next_drop
            else:
                amount = quote_ccy_amount
                buy_first_time = ticker['percentage'] < -float(min_drops_pct[symbol])
            
            if balance < amount:
                msg = f'Insufficient funds for buying the dip. Attempting to buy {quote_ccy} {amount:.2f} of {asset} but only {quote_ccy} {balance:.2f} available.'
                msg += f'\nTrying again in {config["General"]["retry_after"]} minutes...'
                logger.warning(msg)
                if not silent:
                    utils.send_msg(bot_token, config['IM']['telegram_chat_id'], msg)
                time.sleep(config['General']['retry_after'] * 60)
                continue

            if buy_first_time or buy_again:
                order = crypto.place_order(exchange=binance, 
                                            symbol=symbol, 
                                            price=ticker['last'], 
                                            quote_ccy_amount=amount,
                                            order_type='limit',
                                            dry_run=dry_run)
                orders['Non-DCA'][symbol] = order
                if not dry_run:
                    db.save(orders)
                msg = f'Buying ${order["amount"]*order["price"]:.1f} of {symbol} @ {ticker["last"]:,}'
                if buy_again:
                    msg += f': {discount_pct:.1f}% down from previous buy'
                else:
                    msg += f': {ticker["percentage"]:.1f}% lower than 24h ago'
                if config['General']['dry_run']:
                    msg += ' (Dummy mode)'
                logger.info(msg)
                if not silent:
                    utils.send_msg(bot_token, config['IM']['telegram_chat_id'], msg)
            else:
                if recently_bought:
                    previous_price = orders['Non-DCA']['symbol']['price']
                    target_price = orders['Non-DCA']['symbol']['price'] * (1 - min_next_drop/100)
                    msg = f'{symbol} bought recently @ {previous_price:.5f}. '
                    msg += f'Will buy more if it drops to {target_price:.5f} (-{min_next_drop}%)'
                else:
                    msg = f'{symbol} 24h change is {ticker["percentage"]:.1f}%. '
                    msg += f'Will buy if it drops more than -{float(min_drops_pct[symbol]):.2f}%'
                logger.debug(msg)

        logger.debug(f'Checking again for price drops in {freq} minutes...\n')
        time.sleep(freq * 60)


def days_from_last_dca(symbol, orders):
    """Returns the number of days that have passed since the last dca order was placed"""
    if symbol not in orders['DCA']:
        return 10000 # Arbitrary long number meaning too many days / never buoght
    else:
        last_dca_order = orders['DCA'][symbol]
        timestamp = last_dca_order['timestamp']
        
        # In case order timestamp is in milliseconds, convert to seconds
        if timestamp - int(timestamp) == 0:
            timestamp /= 1000
        
        diff = datetime.now() - datetime.fromtimestamp(timestamp)
        return diff.days


def dca(dca_amount, symbol, orders, dca_freq, binance, ticker, dry_run, silent, bot_token):
    """Returns true if it's time to place a new dollar-cost-average (DCA) 
    order given previous orders and frequency in days, false otherwise
    """
    days_since = days_from_last_dca(symbol, orders)
    last_dca_order = orders['DCA'].get(symbol, None)

    if last_dca_order is None or days_since >= dca_freq:
        new_dca_order = crypto.place_order(exchange=binance, 
                                            symbol=symbol, 
                                            price=ticker['last'], 
                                            quote_ccy_amount=dca_amount,
                                            order_type='limit',
                                            dry_run=dry_run)
        orders['DCA'][symbol] = new_dca_order
        if not dry_run:
            db.save(orders)
        msg = f'DCA Buying {new_dca_order["amount"]:.5f} of {symbol} @ {ticker["last"]} '
        msg += f'after {days_since} days from last periodic buy'
        logger.info(msg)
        if not silent:
            utils.send_msg(bot_token, config['IM']['telegram_chat_id'], msg)


if __name__ == '__main__':
    typer.run(main)
