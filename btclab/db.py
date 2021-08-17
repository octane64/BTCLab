import pickle
from btclab import Strategy


def save(orders: dict, strategy: Strategy, dry_run: bool):
    """
    Saves the orders dictionary to a file
    """
    dummy = '_dummy' if dry_run else ''
    filename = strategy.value + '_orders' + dummy + '.pkl'
    pickle.dump(orders, open(filename, 'wb'))
    


def get_orders(strategy: Strategy, dry_run: bool) -> dict:
    """
    Returns a dictionary with the previously saved orders (the most recent for each symbol)
    """ 
    dummy = '_dummy' if dry_run else ''
    filename = strategy.value + '_orders' + dummy + '.pkl'

    try:
        orders = pickle.load(open(filename, 'rb'))
    except FileNotFoundError:
        orders = {}
    
    return orders

