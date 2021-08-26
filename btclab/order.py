from dataclasses import dataclass

from btclab import Strategy

@dataclass
class Order():
    id: str                     # '12345-67890:09876/54321'
    timestamp: int              # 1502962946216, order placing/opening Unix timestamp in milliseconds
    symbol: str                 # 'ETH/BTC', symbol
    order_type: str                   # 'market', 'limit'
    side: str                   # 'buy', 'sell'
    price: float                # 0.06917684, float price in quote currency (may be empty for market orders)
    amount: float               # 1.5, ordered amount of base currency
    cost: float                 # 0.076094524, 'filled' * 'price' (filling price used where available)
    fee: dict                   # fee info, if available {'currency': 'BTC', 'cost': 0.0009, 'rate': 0.002}
    strategy: Strategy
    is_dummy: bool
