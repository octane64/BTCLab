import db
import data
import sys
import logging
import typer
from users import Account
from retry import retry
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, InitVar
from typing import Optional
from logconf import logger
from telegram import TelegramBot
from ccxt.base.errors import InsufficientFunds, NetworkError, RequestTimeout


@dataclass
class Bot():
    accounts: list[Account]

    def _get_all_symbols(self) -> set[str]:
        symbols = []
        for account in self.accounts:
            for symbol in account.dips_manager.dips_config.keys():
                symbols.append(symbol)
        return set(symbols)

    def run(self, dry_run=False):
        symbols_stats = db.get_symbols_stats()

        if not symbols_stats:
            all_symbols = self._get_all_symbols()
            std_devs = data.get_std_dev(self.accounts[0].exchange, all_symbols)
            db.load_symbol_stats(std_devs)
            symbols_stats = std_devs
        
        for account in self.accounts:
            account.dca_manager.buy(account.user_id, account.exchange, account.telegram_bot, dry_run)
            account.dips_manager.buydips(account.user_id, account.exchange, symbols_stats, account.telegram_bot, dry_run)
            # TODO Check balances


def main(frequency: typer.Option(5, '--frequency', '-f', help='Frequency in minutes to check for price drops'),
            verbose: typer.Option(False, '--verbose', '-v', help='Show detailed information')):
    if verbose:
        logger.setLevel(logging.DEBUG)

    accounts = db.get_users()
    bot = Bot(accounts)
    bot.run(frequency)


if __name__ == '__main__':
    # typer.run(main)
    logger.setLevel(logging.DEBUG)

    db.create_db()
    accounts = db.get_users()
    if len(accounts) == 0:
        logger.info('No user accounts found. Create a user account and try again')
        sys.exit(1)

    bot = Bot(accounts)
    bot.run(dry_run=True)
    
    