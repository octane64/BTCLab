import time
import pandas as pd
from typing import List
from datetime import datetime
import utils
import ccxt
import pickle
from datetime import datetime, timedelta


def get_data(exchange, symbols: List[str], num_of_days: int = 1000) -> dict:
    """Returns a dictionary with OHLCV data for the last num_of_days of each symbol
    Data for each days is a list with: [timestamp, open, high, low, close, volume]
    Max 1000 days of data per symbol will be returned
    
    i.e. 
    {
        "ADA/USDT": [
            [1534723200000, 0.10131, 0.10299, 0.09159, 0.09174, 135267717.6],
            [1534809600000, 0.09203, 0.09541, 0.09001, 0.09469, 132327843.8],
            ...
            [1534982400000, 0.08926, 0.0942, 0.08835, 0.09232, 127991686.6]
        ],
        "DOT/USDT": [ 
            [1620086400000, 1.3627, 1.3673, 1.2557, 1.2698, 421500877.62],
            [1620259200000, 1.4799, 1.7, 1.4288, 1.6491, 1342973403.72],
            ...
            [1534982400000, 0.08926, 0.0942, 0.08835, 0.09232, 127991686.6]
        ]
    }
    """

    try:
        data = pickle.load(open('ohlcv.pkl', 'rb'))
    except FileNotFoundError:
        data = {}

    if exchange.has['fetchOHLCV']:
        for symbol in symbols:
            if symbol in data:
                latest_date_ts = data[symbol][-1][0] / 1000
                latest_date = datetime.fromtimestamp(latest_date_ts)
                days_since = (datetime.now() - latest_date).days
                
                # Only retrieve data for the days after the latest day found in ohlcv.pkl for each symbol
                if days_since > 0:
                    time.sleep (exchange.rateLimit / 1000) # time.sleep wants seconds
                    new_data_for_symbol = exchange.fetch_ohlcv(symbol, '1d', limit=days_since)
                    data[symbol].extend(new_data_for_symbol)
            else:
                data[symbol] = exchange.fetch_ohlcv(symbol, '1d', limit=num_of_days)

    pickle.dump(data, open('ohlcv.pkl', 'wb'))

    return data


def get_close_prices(exchange, symbols: List[str], num_of_days: int) -> pd.DataFrame:
    """Returns a Pandas dataframe with close prices for the symbols provided"""
    data = get_data(exchange, symbols, num_of_days)
    
    df = pd.DataFrame(columns=data.keys())
    for symbol in data:
        for ohlcv_row in data[symbol]:
            posix_timestamp = ohlcv_row[0]/1000
            date = datetime.fromtimestamp(posix_timestamp).date()
            close_price = ohlcv_row[3]
            df.loc[date, symbol] = close_price
    
    return df


if __name__ == '__main__':
    config = utils.get_config()
    import os
    binance = ccxt.binance(
        {
            'apiKey': os.environ.get('BINANCE_API_KEY'),
            'secret': os.environ.get('BINANCE_API_SECRET'),
            'enableRateLimit': True,
        }
    )
    
    df = get_close_prices(binance, ['ADA/USDT', 'DOT/USDT', 'BTC/USDT'], 300)
    print(df.tail(15))
    df.to_csv('crypto.csv')
