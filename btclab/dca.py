from dataclasses import dataclass

from btclab.common import Strategy
from btclab.logconf import logger
from btclab.users import Account
from btclab import database
from btclab import crypto


@dataclass
class DCAManager():
    user_account: Account

    def _days_to_buy(self, symbol: str) -> int:
        """
        Returns the number of days left to place a new buy order in a 
        dollar-cost-average (dca) strategy. 
        """
        user_id = self.user_account.user_id
        days_since_last_dca = database.days_from_last_order(user_id, symbol, Strategy.DCA)
        if days_since_last_dca == -1:
            days_left = 0
        else:
            days_left = self.user_account.dca_config[symbol]['days_to_buy_again'] - days_since_last_dca
        
        return days_left

    def _get_dca_buy_msg(self, order):
        """
        Returns a message with the resume of a dca operation
        """

        msg = f'Periodic buys: buying {order["cost"]:.2g} of {order["symbol"]} @ {order["price"]:,.5g}'
        if order['is_dummy']:
            msg += '. (Running in simulation mode, balance was not affected)'
        return msg

    def buy(self, dry_run: bool):
        for symbol, config in self.user_account.dca_config.items():
            cost = config['order_cost']
            user_id = self.user_account.user_id
            days_left = self._days_to_buy(symbol)
            if days_left != 0:
                msg = f'{symbol}: Not time to buy yet. {days_left} day(s) left for the next purchase'
                logger.debug(msg)
                continue
                
            order = crypto.place_buy_order(exchange=self.user_account.exchange, 
                                            symbol=symbol, 
                                            price=None, 
                                            order_cost=cost, 
                                            order_type='market', 
                                            strategy=Strategy.DCA,
                                            is_dummy=config['is_dummy'],
                                            dry_run=dry_run,
                                            user_id=user_id)
            database.save_order(order, user_id, Strategy.DCA)
            
            if order:
                msg = self._get_dca_buy_msg(order)
                logger.info(msg)
                self.user_account.telegram_bot.send_msg(msg)
