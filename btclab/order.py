from dataclasses import dataclass
from datetime import datetime

from common import Strategy



@dataclass
class Order():
    id: str                     # '12345-67890:09876/54321'
    datetime_: datetime              # ISO8601 datetime string with milliseconds
    symbol: str                 # 'ETH/BTC', symbol
    order_type: str             # 'market', 'limit'
    side: str                   # 'buy', 'sell'
    price: float                # 0.06917684, float price in quote currency (may be empty for market orders)
    amount: float               # 1.5, ordered amount of base currency
    cost: float                 # 0.076094524, 'filled' * 'price' (filling price used where available)
    fee: dict                   # fee info, if available {'currency': 'BTC', 'cost': 0.0009, 'rate': 0.002}
    strategy: Strategy
    is_dummy: bool
    user_id: int

    @staticmethod
    def get_dummy_order(user_id, symbol, order_type, side, price, cost, strategy) -> dict:
        """Returns a dictionary with the information of a dummy order. The structure
        is the same as the one returned by the create_order function from ccxt library
        https://ccxt.readthedocs.io/en/latest/manual.html#orders
        """
        right_now = datetime.utcnow()
        order = {
                'id': int(right_now.timestamp()),
                'datetime': right_now.isoformat(),
                'symbol': symbol,
                'type': order_type,
                'side': side,
                'price': price,
                'amount': cost / price, # 
                'cost': cost,
                'strategy': strategy.value,
                'is_dummy': int(True),
                'user_id': user_id,
        }
        return order
