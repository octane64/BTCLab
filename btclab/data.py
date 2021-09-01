import pandas as pd
from retry import retry
from ccxt import NetworkError, RequestTimeout

from btclab.logconf import logger


@retry((NetworkError, RequestTimeout), delay=15, jitter=5, logger=logger)
def get_close_prices(exchange, symbols: list[str]) -> pd.DataFrame:
    """"Returns a Pandas DataFrame with the daily close price of each symbol
    """
    df = None
    if exchange.has['fetchOHLCV']:
        for symbol in symbols:
            data = exchange.fetch_ohlcv(symbol, '1d', limit=1000)
            idx = [x[0] for x in data]
            close_price = [x[3] for x in data]
            new_df = pd.DataFrame(close_price, index=idx, columns=[symbol])
            df = pd.concat([df, new_df], axis=1)
    
    df.index = pd.to_datetime(df.index, unit='ms')
    return df


def get_std_dev(exchange, symbols: list[str], ) -> dict:
    """Returns a dictionary with the standard deviations of each symbol
    """
    close_prices = get_close_prices(exchange, symbols)
    rets = close_prices.pct_change()
    return rets.std().to_dict()