import pickle

def save(orders: dict):
    """Saves the orders dictionary to a file"""
    
    pickle.dump(orders, open('orders.pkl', 'wb'))


def get_orders() -> dict:
    """Returns a dictionary with the orders on disk"""
    
    try:
        orders = pickle.load(open('orders.pkl', 'rb'))
    except FileNotFoundError:
        orders = {'DCA': {}, 'Non-DCA': {}}
    
    return orders

