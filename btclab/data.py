import time
from typing import List
import utils
import ccxt
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

    data = {}
    if exchange.has['fetchOHLCV']:
        for symbol in symbols:
            time.sleep (exchange.rateLimit / 1000) # time.sleep wants seconds
            data[symbol] = exchange.fetch_ohlcv(symbol, '1d', limit=num_of_days)
    return data


if __name__ == '__main__':
    config = utils.get_config()
    
    binance = ccxt.binance(
        {
            'apiKey': config['Exchange']['api_key'],
            'secret': config['Exchange']['api_secret'],
            'enableRateLimit': True,
        }
    )
    
    data = get_data(binance, ['ADA/USDT'], 100)
    import pprint
    pprint.pprint(data['ADA/USDT'])
