from datetime import datetime


def days_from_last_dca(symbol, orders):
    """
    Returns the number of days that have passed since the last dca order 
    was placed or -1 if never been placed
    """
    if symbol not in orders:
        return -1 # Arbitrary long number meaning too many days / never buoght
    else:
        last_dca_order = orders[symbol]
        timestamp = last_dca_order['timestamp'] / 1000
        diff = datetime.now() - datetime.fromtimestamp(timestamp)
        return diff.days


def time_to_buy(symbol, previous_orders, dca_freq):
    """
    Returns true if today is a day to buy in a 
    dollar-cost-average (dca) plan, false otherwise
    """
    
    days_since_last_dca = days_from_last_dca(symbol, previous_orders)
    if days_since_last_dca == -1 or days_since_last_dca >= dca_freq:
        return True
    return False


def get_dca_buy_msg(real_cost, symbol, price, frequency, dry_run):
    """
    Returns a message with the resume of a dca operation
    """

    msg = f'Buying {real_cost:.2f} of {symbol} @ {price:,.5g}'
    msg += f'. Next periodic buy will ocurr in {frequency} days'
    if dry_run:
        msg += '. (Running in simulation mode, balance was not affected)'
    return msg


def get_dca_header(config, symbols, orders, freq):
    title = 'BTCLab crypto engine running for DCA strategy'
    msg = f'\n{"-" * len(title)}\n{title}\n{"-" * len(title)}\n\n'
    
    if len(orders) > 0:
        msg += 'You previously bought:\n'
        for key, value in orders.items():
            timestamp = value['timestamp'] / 1000
            strdate = datetime.fromtimestamp(timestamp).strftime('%x %X')
            msg += f'- {key} -> {value["amount"]:.6g} @ {value["price"]:,.2f} on {strdate}\n'

    msg += '\nRules for execution:\n'
    if config['General']['dry_run']:
        msg += '- Running in simmulation mode, balances will not be affected\n'
    msg += f'- Orders to buy {", ".join(symbols)} will be placed every {freq} days\n\n'
    msg += f'Hit Ctrl + C to stop\n'
    return msg
    
    