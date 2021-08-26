from datetime import datetime
from dataclasses import dataclass
from common import Strategy
from telegram import TelegramBot
from ccxt import Exchange
from logconf import logger
import crypto
import db

@dataclass
class DCAManager():
    dca_config: dict

    def _time_to_buy(self, user_id: str, symbol: str) -> bool:
        """
        Returns true if it's time to buy in a dollar-cost-average (dca)
        strategy, false otherwise
        """
        days_since_last_dca = db.days_from_last_order(user_id, symbol, Strategy.DCA)

        if days_since_last_dca >= self.dca_config[symbol]['days_to_buy_again']:
            return True
        
        days_left = self.dca_config[symbol]['days_to_buy_again'] - days_since_last_dca
        msg = f'User {user_id}: Next periodic buy of {symbol} will occur in {days_left} day(s)'
        logger.debug(msg)
        return False

    def _get_dca_buy_msg(self, order):
        """
        Returns a message with the resume of a dca operation
        """

        msg = f'Buying {order["cost"]:.2g} of {order["symbol"]} @ {order["price"]:,.5g}'
        msg += f'. Next periodic buy will ocurr in {self.frequency} days'
        if self.dry_run:
            msg += '. (Running in simulation mode, balance was not affected)'
        return msg

    def buy(self, user_id: str, exchange: Exchange, telegram_bot: TelegramBot, dry_run: bool):
        for symbol, config in self.dca_config.items():
            cost = config['order_cost']
            if self._time_to_buy(user_id, symbol):
                order = crypto.place_buy_order(exchange, symbol, None, cost, 'market', Strategy.DCA, dry_run)
                db.save_order(order, user_id, Strategy.DCA, dry_run)
                
                if order:
                    msg = self._get_dca_buy_msg(order)
                    logger.info(msg)
                    self.telegram_bot.send_msg(msg)