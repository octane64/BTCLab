import sqlite3
import os
from pathlib import Path
from datetime import datetime
from sqlite3.dbapi2 import Cursor
from dateutil import parser
from sqlite3 import Error, Connection
from typing import Optional

from btclab.common import Strategy
from btclab.order import Order
from btclab.telegram import TelegramBot
from btclab.logconf import logger
from btclab.users import Account


def create_connection() -> Connection:
    """
    Returns a connection to the SQLite database specified by db_file
    """
    if os.getenv('PYTHONPATH') is None:
        db_file = 'database.db'
    else:
        db_file = os.getenv('PYTHONPATH') + 'database.db'
    
    # Make sure data directory has write access for everyone. If not, connect will fail
    os.chmod(db_file, 0o777)
    conn = None
    try:
        conn = sqlite3.connect(db_file)
    except Error as e:
        logger.error(e)

    return conn


def create_table(conn: Connection, sql_statement: str):
    """
    Creates a table from a DDL sql statement 
    """
    try:
        c = conn.cursor()
        c.execute(sql_statement)
    except Error as e:
        logger.error(e)


def create_db():
    """
    Creates the database
    """
    users_table = """
            CREATE TABLE IF NOT EXISTS users (
                user_id integer PRIMARY KEY,
                first_name text NOT NULL,
                last_name text NOT NULL,
                email text NOT NULL UNIQUE,
                is_active integer DEFAULT 1,
                created_on text NOT NULL,
                exchange_id text NOT NULL UNIQUE,
                api_key text NOT NULL UNIQUE,
                api_secret text NOT NULL UNIQUE,
                telegram_bot_token text UNIQUE,
                telegram_chat_id text UNIQUE,
                notify_to_telegram integer DEFAULT 1,
                notify_to_email integer DEFAULT 0
            );"""
    
    dca_config_table = """
        CREATE TABLE IF NOT EXISTS dca_config (
            user_id integer NOT NULL,
            symbol text NOT NULL,
            order_cost real NOT NULL,
            days_to_buy_again integer NOT NULL,
            is_active integer DEFAULT 1,
            is_dummy integer DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        );"""

    dip_config_table = """
        CREATE TABLE IF NOT EXISTS dip_config (
            user_id integer NOT NULL,
            symbol text NOT NULL,
            order_cost real NOT NULL,
            min_drop_value real NOT NULL,
            min_drop_units text NOT NULL,
            min_additional_drop_pct real NOT NULL,
            additional_drop_cost_increase real DEFAULT 0,
            is_active integer DEFAULT 1,
            is_dummy integer DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        );"""

    orders_table = """
        CREATE TABLE IF NOT EXISTS orders (
            order_id text,
            clientOrderId,
            timestamp integer NOT NULL,
            symbol text NOT NULL,
            type text NOT NULL,
            side text NOT NULL,
            price real,
            amount real, 
            cost real,
            strategy text NOT NULL,
            is_dummy integer NOT NULL,
            user_id integer NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        );"""

    symbols_stats_table = """
        CREATE TABLE IF NOT EXISTS symbols_stats (
            symbol text NOT NULL,
            std_dev real NOT NULL,
            updated_on integer NOT NULL,
            comments text
        );"""

    # create tables
    conn = create_connection()
    if conn is not None:
        create_table(conn, users_table)
        create_table(conn, dca_config_table)
        create_table(conn, dip_config_table)
        create_table(conn, orders_table)
        create_table(conn, symbols_stats_table)
        conn.close()
    else:
        logger.error("Error! cannot create the database connection.")


def get_users() -> list[Account]:
    """
    Return the list of active user accounts from the databse
    """
    conn = create_connection()
    cur = conn.cursor()
    sql = """SELECT
                user_id,
                first_name,
                last_name,
                email,
                created_on,
                exchange_id,
                api_key,
                api_secret,
                telegram_bot_token,
                telegram_chat_id,
                notify_to_telegram,
                notify_to_email
            FROM users
            WHERE is_active = 1
            """
    
    try:
        cur.execute(sql)
        rows = cur.fetchall()
    except sqlite3.Error as error:
        logger.error(f'Failed to retrieve latest order for users from database')
        raise error
    finally:
        cur.close()
        conn.close()
    
    accounts = []
    for row in rows:
        telegram_bot = TelegramBot(row[8], row[9])
        dca_config = get_dca_config(row[0])
        dips_config = get_dip_config(row[0])
        
        user_account = Account(user_id=row[0],
                                first_name=row[1], 
                                last_name=row[2],
                                email=row[3],
                                created_on=parser.parse(row[4]),
                                exchange_id=row[5],
                                api_key=row[6],
                                api_secret=row[7], 
                                telegram_bot=telegram_bot,
                                notify_to_telegram=bool(row[10]),
                                notify_to_email=bool(row[11]),
                                dca_config=dca_config,
                                dips_config=dips_config)
        
        accounts.append(user_account)

    logger.debug(f'Active user account(s) found in database: {len(accounts)}')

    return accounts


def get_dca_config(user_id: str) -> dict:
    """
    Returns a dictionary with the active configuration params that user_id has set for recurrent buys (dca)
    """
    conn = create_connection()
    cur = conn.cursor()
    sql = """SELECT
                symbol,
                order_cost,
                days_to_buy_again,
                is_dummy
            FROM dca_config
            WHERE user_id = ? AND is_active = 1
            """
    try:
        cur.execute(sql, (user_id, ))
        rows = cur.fetchall()
    except sqlite3.Error as error:
        logger.debug(f'Error while retrieving DCA params for user {user_id}')
        raise error
    finally:
        cur.close()
        conn.close()

    dca_config = {}
    for row in rows:
        dca_config[row[0]] = {
            'order_cost': row[1], 
            'days_to_buy_again': row[2],
            'is_dummy': row[3],
        }
    
    return dca_config


def get_dip_config(user_id: str) -> dict:
    """
    Returns a dictionary with the active configuration params that user_id has set for buying dips
    """
    conn = create_connection()
    cur = conn.cursor()
    sql = """SELECT
                symbol,
                order_cost,
                min_drop_value,
                min_drop_units,
                min_additional_drop_pct,
                additional_drop_cost_increase,
                is_dummy
            FROM dip_config
            WHERE user_id = ? AND is_active = 1
            """
    try:
        cur.execute(sql, (user_id, ))
        rows = cur.fetchall()
    except sqlite3.Error as error:
        logger.debug(f'Error while retrieving dip params for user {user_id}')
        raise error
    finally:
        cur.close()
        conn.close()

    dip_config = {}
    for row in rows:
        dip_config[row[0]] = {
            'order_cost': row[1], 
            'min_drop_value': row[2],
            'min_drop_units': row[3],
            'min_additional_drop_pct': row[4],
            'additional_drop_cost_increase': row[5],
            'is_dummy': row[6]
        }
    
    return dip_config


def get_latest_order(user_id: str, symbol: str, strategy: Strategy = None) -> Optional[Order]:
    """
    Returns the latest order of a user for a given strategy
    """
    conn = create_connection()
    cur = conn.cursor()
    where_clause = 'AND strategy = ?' if strategy else ''
    sql = f"""SELECT
                order_id,
                timestamp,
                symbol,
                type,
                side,
                price,
                amount,
                cost,
                strategy,
                is_dummy
            FROM orders
            WHERE user_id = ? AND symbol = ? {where_clause} 
            ORDER BY timestamp DESC
            LIMIT 1
            """
    
    try:
        if strategy:
            cur.execute(sql, (user_id, symbol, strategy.value))
        else:
            cur.execute(sql, (user_id, symbol))
        row = cur.fetchone()
    except sqlite3.Error as error:
        logger.error(f'Failed to retrieve latest order of user {user_id}')
        raise error
    finally:
        cur.close()
        conn.close()

    if row is None:
        return None

    order = Order(id=row[0],
                    timestamp=row[1],
                    symbol=row[2],
                    order_type=row[3],
                    side=row[4],
                    price=row[5],
                    amount=row[6],
                    cost=row[7],
                    fee=None,
                    strategy=strategy.value,
                    is_dummy=bool(row[8]))
    return order


def save_order(order: dict, user_id:str, strategy: Strategy):
    conn = create_connection()
    sql = """
            INSERT INTO orders (order_id, timestamp, symbol, type, side, price, 
                                amount, cost, strategy, is_dummy, user_id) 
            
            VALUES (:order_id, :timestamp, :symbol, :type, :side, :price, 
                    :amount, :cost, :strategy, :is_dummy, :user_id) """
    
    values = {
        'order_id': order['id'],
        'timestamp': order['timestamp'],
        'symbol': order['symbol'],
        'type': order['type'],
        'side': order['side'],
        'price': order['price'],
        'amount': order['amount'],
        'cost': order['cost'],
        'strategy': strategy.value,
        'is_dummy': int(order['is_dummy']),
        'user_id': user_id
    }
    
    try:
        cur = conn.cursor()
        cur.execute(sql, values)
        conn.commit()
        logger.debug(f'Order to {order["side"]} {order["symbol"]} saved with id {order["id"]}')
    except sqlite3.Error as error:
        logger.error(f'Failed to save order with id {order["id"]}')
        raise error
    finally:
        cur.close()
        conn.close()


def days_from_last_order(user_id: str, symbol: str, strategy: Strategy) -> int:
    """
    Returns the number of days that have passed since the last order was placed for symbol, 
    strategy and user, or -1 if no orders have been placed
    """
    last_order = get_latest_order(user_id, symbol, strategy)
    if last_order is None:
        return -1
    
    order_date = datetime.fromtimestamp(last_order.timestamp)
    diff = datetime.now() - order_date
    return diff.days


def get_symbols() -> set[str]:
    conn = create_connection()
    sql = """SELECT DISTINCT symbol FROM dip_config"""
    cur = conn.cursor()

    try:
        cur.execute(sql)
        rows = cur.fetchall()
    except sqlite3.Error as error:
        logger.error(error)
        raise error
    finally:
        cur.close()
        conn.close()
    
    symbols = set([item for row in rows for item in row])
    return symbols


def load_symbol_stats(stats: dict):
    conn = create_connection()
    cur = conn.cursor()
    symbols = get_symbols()

    sql_update = """UPDATE symbols_stats 
            SET std_dev = ?, 
                updated_on = datetime('now', 'localtime')
            WHERE symbol = ? """

    sql_insert = """INSERT INTO symbols_stats (symbol, std_dev, updated_on) 
                VALUES (?, ?, datetime('now', 'localtime')) """

    try:
        for symbol in symbols:
            update_result = cur.execute(sql_update, (symbol, stats[symbol]))
            if update_result.rowcount ==0:
                update_result = cur.execute(sql_insert, (symbol, stats[symbol]))
        conn.commit()
    except sqlite3.Error as error:
        logger.error(error)
        raise error
    finally:
        cur.close()
        conn.close()


def get_symbols_stats() -> dict:
    """
    Returns a dictionary with the statistics for symbols in the dip_config table
    """
    conn = create_connection()
    cur = conn.cursor()
    sql = """SELECT
                symbol,
                std_dev,
                updated_on
            FROM symbols_stats"""
    try:
        cur.execute(sql)
        rows = cur.fetchall()
    except sqlite3.Error as error:
        logger.debug('Error while retrieving symbols stats')
        raise error
    finally:
        cur.close()
        conn.close()

    symbols = {}
    for row in rows:
        symbols[row[0]] = {'std_dev': row[1], 'updated_on': row[2]}
    
    return symbols
