import sys
import logging
import click
from dataclasses import dataclass

from btclab import __version__
from btclab.dca import DCAManager
from btclab.dips import DipsManager
from btclab.users import Account
from btclab import data
from btclab import database


log_format = '%(asctime)s - %(levelname)-8s - %(message)s'
logging.basicConfig(level=logging.INFO, format=log_format, datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger()

@dataclass
class Bot():
    accounts: list[Account]

    def _get_all_symbols(self) -> set[str]:
        symbols = []
        tmp = database.get_symbols_stats()
        if tmp:
            symbols = tmp.keys()

        return set(symbols)

    def run(self, dry_run: bool):
        for account in self.accounts:
            if dry_run:
                logger.info('Running in simmulation mode. Balances will not be affected')
            logger.info(f'Checking information for user with id {account.user_id}')
            
            summary = account.get_summary()
            if summary:
                account.telegram_bot.send_msg(summary)
                database.update_last_contact(account.user_id)

            if account.dca_config:
                logger.info(f'Checking recurrent purchases for the DCA strategy')
                dca_manager = DCAManager(account)
                dca_manager.buy(dry_run)
            else:
                logger.info(f'No DCA config found for user id {account.user_id}')
            
            if account.dips_config:
                logger.info(f'Checking price drops for the dip buying strategy')
                all_symbols = database.get_symbols()
                symbols_stats = database.get_symbols_stats() # TODO Calculate again if older than x days
                if not symbols_stats or not all(symbol in symbols_stats for symbol in all_symbols):
                    logger.info(f'Getting information for symbols {", ".join(all_symbols)}')
                    std_devs = data.get_std_dev(account.exchange, all_symbols)
                    database.load_symbol_stats(std_devs)
                    symbols_stats = database.get_symbols_stats()
                
                
                dips_manager = DipsManager(account)
                dips_manager.buy_dips(symbols_stats, dry_run)
            else:
                logger.info(f'No dips config found for user id {account.user_id}')


@click.command()
@click.option('-v', '--verbose', is_flag=True, help="Print verbose messages while excecuting")
@click.option('--dry-run', is_flag=True, help="Run in simulation mode (Don't affect balances)")
def main(verbose, dry_run):
    logger.info(f'BTCLab version {__version__}')
    if verbose:
        logger.setLevel(logging.DEBUG)

    database.create_db()
    accounts = database.get_users()
    if len(accounts) == 0:
        logger.info('No user accounts found. Create a user account and try again')
        sys.exit()

    bot = Bot(accounts)
    bot.run(dry_run)


if __name__ == '__main__':
    main()









    
    
    