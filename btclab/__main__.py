import sys
import logging
import click
from enum import Enum
from retry import retry
from typing import Optional
from datetime import datetime
from dataclasses import dataclass, InitVar
from ccxt.base.errors import InsufficientFunds, NetworkError, RequestTimeout

from btclab.dca import DCAManager
from btclab.dips import DipsManager
from btclab.users import Account
from btclab.logconf import logger
from btclab.telegram import TelegramBot
from btclab import data
from btclab import database


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
        symbols_stats = database.get_symbols_stats()

        if not symbols_stats:
            all_symbols = self._get_all_symbols()
            logger.debug(f'Getting information for symbols {", ".join(all_symbols)}')
            std_devs = data.get_std_dev(self.accounts[0].exchange, all_symbols)
            database.load_symbol_stats(std_devs)
            symbols_stats = std_devs
        
        for account in self.accounts:
            logger.debug(f'Checking information for user id: {account.user_id}')
            logger.debug(f'Checking days since last buy for the DCA strategy)')
            dca_manager = DCAManager(account)
            dca_manager.buy(dry_run)
            
            logger.debug(f'Checking price drops for the dip buying strategy)')
            dips_manager = DipsManager(account)
            dips_manager.buydips(symbols_stats, dry_run)
            # TODO Check balances


@click.command()
@click.option('-v', '--verbose', default=True, is_flag=True, help="Print verbose messages while excecuting")
@click.option('--dry-run', is_flag=True, help="Run in simmulation mode. (Don't place real orders)")
def main(dry_run, verbose):
    if verbose:
        logger.setLevel(logging.DEBUG)

    database.create_db()
    accounts = database.get_users()
    if len(accounts) == 0:
        logger.info('No user accounts found. Create a user account and try again')
        sys.exit(1)

    bot = Bot(accounts)
    bot.run(dry_run)


if __name__ == '__main__':
    main()
    # logger.setLevel(logging.DEBUG)

    
    
    