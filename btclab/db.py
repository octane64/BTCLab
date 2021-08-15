import pickle
from crypto import Strategy


def save(orders: dict, strategy: Strategy):
    """Saves the orders dictionary to a file"""
    
    pickle.dump(orders, open(strategy.value + '_orders.pkl', 'wb'))
    


def get_orders(order_type: Strategy) -> dict:
    """Returns a dictionary with the previously saved orders (the most recent for each symbol) """
    
    try:
        orders = pickle.load(open(order_type.value + '_orders.pkl', 'rb'))
    except FileNotFoundError:
        orders = {}
    
    return orders

