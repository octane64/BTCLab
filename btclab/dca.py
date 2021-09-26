import logging
from datetime import datetime
from dataclasses import dataclass
from dateutil import parser 
from ccxt.base.errors import InsufficientFunds

from btclab.common import Strategy
from btclab.users import Account
from btclab import database
from btclab import crypto


logger = logging.getLogger(__name__)

@dataclass
class DCAManager():
    user_account: Account

    def _days_to_buy(self, symbol: str, is_dummy: bool) -> int:
        """
        Returns the number of days left to place a new buy order in a 
        dollar-cost-average (dca) strategy. 
        """
        time_since_last_dca = self.user_account.time_since_last_order(symbol, Strategy.DCA, is_dummy)
        if time_since_last_dca is None:
            days_left = 0
        else:
            days_left = self.user_account.dca_config[symbol]['frequency'] - (time_since_last_dca.seconds / 60 / 60)
        
        return days_left

    def _get_dca_buy_msg(self, order):
        """
        Returns a message with the resume of a dca operation
        """

        msg = f'Periodic buys: buying {order["cost"]:.2g} of {order["symbol"]} @ {order["price"]:,.5g}'
        if order['is_dummy']:
            msg += '. (Simulation)'
        return msg

    def buy(self, dry_run: bool):
        for symbol, config in self.user_account.dca_config.items():
            cost = config['order_cost']
            user_id = self.user_account.user_id
            days_left = self._days_to_buy(symbol, config['is_dummy'])
            
            if days_left != 0:
                time_remaining = f'{days_left/24:.0f} horas' if days_left <= 1 else f'{days_left:.1f} days'
                msg = f'Next purchase of {symbol} will occur in {time_remaining}'
                logger.info(msg)
                continue

            if config['last_check_result'] == 'Insufficient funds':
                last_check = parser.parse(config['last_check_date'])
                time_since_last_check = datetime.now() - last_check
                minutes = (time_since_last_check.seconds // 60) % 60
                if minutes < 30:
                    logger.info(f'Waiting {minutes} more minutes to check again for dips in {symbol} after insufficient funds')
                    continue

            try:
                order = crypto.place_buy_order(exchange=self.user_account.exchange, 
                                                symbol=symbol, 
                                                price=None, 
                                                order_cost=cost, 
                                                order_type='market', 
                                                strategy=Strategy.DCA,
                                                is_dummy=config['is_dummy'],
                                                dry_run=dry_run,
                                                user_id=user_id)
            except InsufficientFunds:
                database.update_last_check(self.user_account.user_id, symbol, Strategy.DCA, 'Insufficient funds')
                quote_ccy = symbol.split('/')[1]
                base_ccy = symbol.split('/')[0]
                msg = f'Insufficient funds to buy {cost:.1f} {quote_ccy} of {base_ccy}. Trying again in 30 minutes'
                logger.info(msg)
                self.user_account.telegram_bot.send_msg(msg)
                continue

            if order:
                msg = self._get_dca_buy_msg(order)
                logger.info(msg)
                self.user_account.telegram_bot.send_msg(msg)
                database.save_order(order, Strategy.DCA)
                database.update_last_check(self.user_account.user_id, symbol, Strategy.DCA, 'Order placed')
