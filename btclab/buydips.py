import os
import time
import logging
import ccxt
import typer
import logging
import crypto
import utils
import data
import db
from logconf import logger
from retry.api import retry, retry_call
# from datetime import datetime, timedelta
from ccxt.base.errors import InsufficientFunds, NetworkError, RequestTimeout


config = utils.get_config()


def print_header(symbols, freq,  amount_usd, increase_amount_by, min_drop, min_next_drop, dry_run, quote_currency, orders):
    title = 'Crypto prices monitor running'
    print(f'\n{"-" * len(title)}\n{title}\n{"-" * len(title)}')
    
    start_msg = 'Starting new session'
    if dry_run:
        start_msg += ' (Running in simmulation mode)'
    print()
    print(start_msg)
    print(f'- Tracking price drops in: {", ".join(symbols)}')
    print(f'- Min drop level set to {min_drop}% for the first buy')
    print(f'- Additional drop level of {min_next_drop}% for symbols already bought')
    print(f'- The amount to buy on each order will be {amount_usd} {quote_currency}')
    if increase_amount_by > 0:
        print(f'- Amount will increase by {increase_amount_by} {quote_currency} on orders of previoulsy bought symbols')
    print('- Run with --verbose option to see more detail')
    print('- Run with --help to see all options\n')

    if orders:
        print('You previously bought:')
        for key, value in orders.items():
            print(f'- {key} -> {value["amount"]} @ {value["price"]}')

    print(f'\nChecking for new price drops every {freq} minutes... Hit Ctrl + C to exit')
    typer.echo()


@retry((RequestTimeout, NetworkError), delay=15, jitter=5, logger=logger)
def main(
        symbols: list[str] = typer.Argument(None, 
            help='The symbols you want to buy if they dip enough, separated by spaces. Either use pairs like '\
                 'BTC/USDT ETH/USDT or main symbols withouth a quote currency. e.g: BTC ETH', show_default=False),
        amount_usd: float = typer.Option(config['General']['order_amount_usd'], '--amount-usd', '-a', 
            help='Amount to buy of symbol in base currency'), 
        increase_amount_by: float = typer.Option(config['General']['increase_amount_by'], '--increase-amount-by', '-i', 
            help='The increase in the amount to buy when a symbol was already bought in the last 24 hours'), 
        freq: float = typer.Option(config['General']['frequency'], '--freq', '-f',
            help='Frequency in minutes to check for new price drops'),
        min_drop: float = typer.Option(config['General']['min_drop'], '--min-drop', '-m', 
            help='Min drop in percentage in the last 24 hours for placing a buy order'),
        min_next_drop: float = typer.Option(config['General']['min_next_drop'], '--min-next-drop', '-n',
            help='The min additional drop in percentage to buy a symbol previoulsy bought'),
        quote_currency: str = typer.Option('USDT', help='Quote currency to use when none is given in symbols list'),
        dry_run: bool = typer.Option(config['General']['dry_run'], 
            help='Run in simmulation mode. Don\'t buy anything'),
        reset_cache: bool = typer.Option(False, '--reset-cache', '-r', help='Reset info of previous operations'),
        silent: bool = typer.Option(False, '--silent', '-s', help='Silent mode. Do not send notifications to chat'),
        verbose: bool = typer.Option(False, '--verbose', '-v', help='Verbose mode')):

    """
    Example usage:
    python buydips.py BTC ETH DOT --freq 10 --min-drop 7 --min-aditional-drop 2

    Start checking prices of BTC/USDT ETH/USDT and DOT/USDT every 10 minutes
    Buy the ones with a drop in the last 24h greater than 7%
    If a symbols was previouly bought, buy again only if it is down 2% from last buy price
    """

    if verbose:
        logger.setLevel(logging.DEBUG)

    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    if bot_token is None:
        bot_token = config['IM']['telegram_bot_token']
    if bot_token is None:
        logging.error('Set the Telegram bot token in the config.yaml or in the TELEGRAM_BOT_TOKEN environment variable')
        raise typer.Exit(code=-1)

    chat_id = config['IM']['telegram_chat_id']
    
    if not symbols:
        symbols = config['General']['tickers']
    
    symbols = [s.upper() for s in symbols]
    symbols = [f'{s}/{quote_currency}' if '/' not in s else s for s in symbols]
    
    api_key = os.environ.get('BINANCE_API_KEY')
    api_secret = os.environ.get('BINANCE_API_SECRET')
    if api_key is None or api_secret is None:
        msg = ('Add your credentials to BINANCE_API_KEY and BINANCE_API_SECRET '
                'environment variables to stop being asked on every execution')
        logger.warning()

    if api_key is None:
        api_key = typer.prompt('Enter your Binance API key').trim()

    if api_secret is None:
        api_secret = typer.prompt('Enter your Binance API secret').trim()

    # print_header(symbols, freq, amount_usd, min_drop, min_next_drop, dry_run)
    binance = ccxt.binance(
        {
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
        }
    )

    # Check if symbols are supported by the exchange
    non_supported_symbols = crypto.get_non_supported_symbols(binance, symbols)
    if len(non_supported_symbols) > 0:
        logging.error((f'The following symbol(s) are not supported in {binance.name}: '
                            f'{", ".join(non_supported_symbols)}. Execution stoped\n'))
        raise typer.Exit(code=-1)

    # Load previous orders
    if reset_cache:
        orders = {}
        db.save(orders)
    else:
        orders = db.get_orders()

    if min_drop == -1:
        std_devs = data.get_std_dev(binance, symbols)

    print_header(symbols, freq, amount_usd, increase_amount_by, min_drop, min_next_drop, dry_run, quote_currency, orders)

    while True:
        tickers = binance.fetch_tickers(symbols)
        # now = datetime.now().strftime('%m/%d/%Y, %H:%M:%S')
        # print(f'Last check: {now} - Hit Ctrl + C to exit', end='\r')
        
        for symbol, ticker in tickers.items():
            buy_first_time = False
            buy_again = False

            if min_drop == -1:
                min_drop = std_devs[symbol] * 100 * 2 # Two standard deviations

            if symbol in orders and crypto.bought_less_than_24h_ago(symbol, orders, dry_run):
                discount_pct = (ticker['last'] / orders[symbol]['price'] - 1) * 100
                buy_again = discount_pct < -min_next_drop
            else:
                buy_first_time = ticker['percentage'] < -min_drop
            
            if buy_first_time or buy_again:
                try:
                    order = crypto.place_order(exchange=binance, 
                                                symbol=symbol, 
                                                price=ticker['last'], 
                                                amount_in_usd=amount_usd,
                                                previous_orders=orders,
                                                increase_amount_by=increase_amount_by,
                                                dry_run=dry_run)
                except InsufficientFunds:
                    retry_after = config['General']['retry_after']
                    msg = f'Insufficient funds. Trying again in {retry_after} minutes...'
                    logger.warning(msg)
                    if not silent:
                        utils.send_msg(bot_token, chat_id, msg)
                    time.sleep(retry_after * 60)
                    continue
                else:
                    orders[symbol] = order
                    db.save(orders)
                    msg = f'Buying ${order["amount"]*order["price"]:.1f} of {symbol} @ {ticker["last"]:,}'
                    if buy_again:
                        msg += f': {discount_pct:.1f}% down from previous buy'
                    else:
                        msg += f': {ticker["percentage"]:.1f}% lower than 24h ago'
                    if dry_run:
                        msg += ' (Dummy mode)'
                    logger.info(msg)
                    if not silent:
                        utils.send_msg(bot_token, chat_id, msg)
            else:
                logger.debug(f'{symbol} currently selling at {ticker["last"]} ({ticker["percentage"]:.1f}%)')

        logger.debug(f'Checking again for price drops in {freq} minutes...\n')
        time.sleep(freq * 60)


if __name__ == '__main__':
    typer.run(main)