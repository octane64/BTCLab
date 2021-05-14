import time
import logging
import ccxt
from retry.api import retry
import typer
import logging
from typing import List
import crypto
import utils
import db
from datetime import datetime, timedelta
from ccxt.base.errors import InsufficientFunds, RequestTimeout


config = utils.get_config()

# Set up logging
logger = logging.getLogger(__name__)
c_handler = logging.StreamHandler()
f_handler = logging.FileHandler('app.log')
c_handler.setLevel(logging.DEBUG)
f_handler.setLevel(logging.ERROR)

fmt = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
c_format = logging.Formatter(fmt='%(asctime)s - %(levelname)s - %(message)s', datefmt='%d-%b-%y %H:%M:%S')
f_format = logging.Formatter(fmt=fmt, datefmt='%d-%b-%y %H:%M:%S')

c_handler.setFormatter(c_format)
f_handler.setFormatter(f_format)

logger.addHandler(c_handler)
logger.addHandler(f_handler)
logger.setLevel(logging.INFO)

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
        timestamp = orders[symbol]['timestamp']
        if '.' not in str(timestamp):
            timestamp /= 1000
        bought_on = datetime.fromtimestamp(timestamp)
        diff = now - bought_on
        return diff.days <= 1
    return False


@retry(RequestTimeout, tries=5, delay=10, backoff=2)
def main(
        symbols: List[str] = typer.Argument(None, 
            help='The symbols you want to buy if they dip enough. e.g: BTC/USDT, ETH/USDC', show_default=False),
        amount_usd: float = typer.Option(config['General']['order_amount_usd'], '--amount-usd', 
            help='Amount to buy of symbol in base currency'), 
        freq: float = typer.Option(config['General']['frequency'], 
            help='Frequency in minutes to check for new price drops'),
        min_drop: float = typer.Option(config['General']['min_initial_drop'],
            help='Min drop in percentage in the last 24 hours for placing a buy order'),
        min_additional_drop: float = typer.Option(config['General']['min_additional_drop'],
            help='The min additional drop in percentage to buy a symbol previoulsy bought'),
        quote_currency: str = typer.Option('USDT', help='Quote curreny to use when none is given in symbols list'),
        dry_run: bool = typer.Option(config['General']['dry_run'], 
            help='Run in simmulation mode. Don\'t buy anything'),
        reset_cache: bool = typer.Option(False, help='Reset info of previous operations'),
        verbose: bool = typer.Option(False, help='Verbose mode')):

    """
    Example usage:
    python buydips BTC/USDT ETH/USDT DOT/USDT --freq 10 --min-drop 7 --min-aditional-drop 2

    Start checking prices of BTC/USDT ETH/USDT and DOT/USDT every 10 minutes
    Buy the one with the biggest drop in the last 24h if that drop is bigger than 7% 
    If the biggest drop is in a symbol previouly bought, buy again only if it is down 2% from last buy price
    """

    if verbose:
        logger.setLevel(logging.DEBUG)

    bot_token = config['IM']['telegram_bot_token']
    chat_id = config['IM']['telegram_chat_id']
    
    if not symbols:
        symbols = config['General']['tickers']
    
    symbols = [s.upper() for s in symbols]
    symbols = [f'{s}/{quote_currency}' if '/' not in s else s for s in symbols ]

    start_msg = 'Starting new session'
    if dry_run:
        start_msg += ' (Running in simmulation mode)'
    typer.echo('\n')
    logger.info(start_msg)
    
    # print_header(symbols, freq, amount_usd, min_drop, min_additional_drop, dry_run)
    binance = ccxt.binance(
        {
            'apiKey': config['Exchange']['api_key'],
            'secret': config['Exchange']['api_secret'],
            'enableRateLimit': True,
        }
    )

    # Check if symbols are supported by the exchange
    non_supported_symbols = crypto.get_unsupported_symbols(binance, symbols)
    if len(non_supported_symbols) > 0:
        logging.error((f'The following symbol(s) are not supported in {binance.name}: '
                            f'{", ".join(non_supported_symbols)}. Execution stoped\n'))
        raise typer.Exit(code=-1)

    # Load previous orders
    orders = db.get_orders() if not reset_cache else {}

    logger.info(f'Tracking price drops in: {", ".join(symbols)}')
    logger.info(f'Min drop level set to {min_drop}% for the first buy')
    logger.info(f'Additional drop level of {min_additional_drop}% for symbols already bought')
    typer.echo()

    while True:
        tickers = binance.fetch_tickers(symbols)
        
        for symbol, ticker in tickers.items():
            buy_first_time = False
            buy_again = False
            if symbol in orders and bought_less_than_24h_ago(symbol, orders):
                discount_pct = (ticker['last'] / orders[symbol]['price'] - 1) * 100
                buy_again = discount_pct < -min_additional_drop
                if buy_again:
                    logger.debug(f'Buying again {symbol}, current price is {discount_pct:.1f}% lower')
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
                    logger.warning(f'Insufficient funds. Trying again in {freq} minutes...')
                else:
                    orders[symbol] = order
                    db.save(orders)
                    msg = crypto.short_summary(order, ticker['percentage'])
                    logger.info(msg)
                    utils.send_msg(bot_token, chat_id, msg)
            else:
                logger.debug(f'{symbol} currently selling at {ticker["last"]} ({ticker["percentage"]:.1f}%) - Not enough discount')
                
        logger.debug(f'Checking again for price drops in {freq} minutes...')
        typer.echo()
        time.sleep(freq * 60)


if __name__ == '__main__':
    typer.run(main)