import logging
import crypto
import utils
import data
from datetime import datetime
from logconf import logger


def buy_initial_drop(exchange, ticker, order_cost, min_drop, orders, config):
    """
    Places a new buy order if symbol hasn't been bought and last 24h drop surpasses the min_drop_pct limit
    """
    symbol = ticker['symbol']
    cost = config['General']['order_cost']
    if symbol not in orders and ticker['percentage'] < -min_drop:
        asset = symbol.split('/')[0]
        quote_ccy = symbol.split('/')[1]
        price = ticker['last']
        order = crypto.place_buy_order(exchange, symbol, price, cost, 'market', config['General']['dry_run'])
        if order: 
            real_cost = order['cost']
        
        msg = (f'Buying {real_cost:,.2g} {quote_ccy} of {asset} @ {price:,.6g}. '
               f'Drop in last 24h is {ticker["percentage"]:.2f}%')
        
        if config['General']['dry_run']:
            msg += '. (Running in simulation mode, balance was not affected)'
        
        logger.debug(msg)
        utils.send_msg(config['IM']['telegram_bot_token'], config['IM']['telegram_chat_id'], msg)
        return order
    
    return None


def buy_additional_drop(exchange, ticker, orders, config):
    """
    Places a new buy order if symbol has been bought recently and last 24h drop surpasses the min_next_drop limit
    """
    symbol = ticker['symbol']
    if crypto.bought_within_the_last(24, symbol, orders):
        drop_from_last_order = (ticker['ask'] / orders[symbol]['price'] - 1) * 100
        
        if drop_from_last_order < -config['General']['min_next_drop']:
            asset = symbol.split('/')[0]
            quote_ccy = symbol.split('/')[1]
            price = ticker['ask']

            cost_of_previous_order = orders[symbol]['cost']
            cost = cost_of_previous_order + config['General']['increase_cost_by']
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


def get_buydips_header(config, symbols, min_drop_pct, orders):
    freq = config['General']['frequency']
    order_cost = config['General']['frequency']
    min_drop = config['General']['min_drop']
    min_next_drop = config['General']['min_next_drop']
    dry_run = config['General']['dry_run']
    
    title = 'BTCLab crypto engine running for dip buying strategy'
    msg = f'\n{"-" * len(title)}\n{title}\n{"-" * len(title)}\n\n'

    if len(orders) > 0:
        msg += 'You previously bought on price dips:\n\n'
        for key, value in orders.items():
            # In case order timestamp is in milliseconds, convert to seconds
            timestamp = value['timestamp'] / 1000
            strdate = datetime.fromtimestamp(timestamp).strftime('%x %X')
            msg += f' - {key} -> {value["amount"]:.6g} @ {value["price"]:,.2f} on {strdate}\n'

    msg += '\nRules for execution:\n'
    msg += f'\n - Tracking price drops in: {", ".join(symbols)} every {freq } minutes\n'
    
    msg_min_drop = std_devs_as_pct_str(min_drop, symbols, min_drop_pct)

    if dry_run:
        msg += ' - Running in simmulation mode, balances will not be affected\n'
    msg += f' - First order will be placed if prices drop at least {msg_min_drop} from last 24 hours\n'
    msg += f' - Additional orders will be placed on drops of at least {min_next_drop}% from last purchase price\n'
    msg += f' - The amount to buy on each order will be {order_cost} of quote currency\n'
    
    increase = config['General']['increase_cost_by']
    if increase > 0:
        msg += f'- Amount will increase by {increase} for previoulsy bought symbols with additional drops\n'

    return msg