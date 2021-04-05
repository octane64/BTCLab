import time
from datetime import datetime
from dataclasses import dataclass
from playsound import playsound
from exchange import Order
import secrets
import utils
import exchange
import click


sender_email = "jcvelasquez903@gmail.com"
receiver_email = "velasquez.gaviria@gmail.com"

def get_alert_msg(bid_order: Order, ask_order: Order, trm: float):
    spread = bid_order.usd_price - ask_order.usd_price
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    link = ask_order.get_link_to_add()
    
    msg = (f'Date:\t\t{timestamp}\n'
            f'Spread:\t\tUSD {spread:,.0f} (COP {spread * trm:,.0f})\n'
            f'Min ask:\tUSD {ask_order.usd_price:,.0f} (COP {ask_order.usd_price * trm:,.0f}) - {ask_order.exchange_name}\n'
            f'Max bid:\tUSD {bid_order.usd_price:,.0f} (COP {bid_order.usd_price * trm:,.0f}) - {bid_order.exchange_name}\n'
            )
            
    if isinstance(ask_order, exchange.LocalBitcoinOrder):
        msg += f'Seller:\t\t{ask_order.profile.name}\nAdd Link:\t{link}\n'
    elif isinstance(bid_order, exchange.LocalBitcoinOrder):
        msg += f'Buyer:\t\t{bid_order.profile.name}\nAdd Link:\t{link}\n'
    
    return msg


def print_review_hdr():
    date_and_time = time.strftime('%Y-%m-%d %X')
    s = date_and_time.center(60, '-')
    print()
    print(s)


def get_exchanges():
    lbc_hmac_key = secrets.keys('lbc_hmac_key')
    lbc_hmac_secret = secrets.keys('lbc_hmac_secret')
    # binance_key = secrets.keys('binance_key')
    # binance_secret = secrets.keys('binance_secret')
    
    exchanges = []
    exchanges.append(exchange.get_exchange(exchange_id='LocalBitcoins', api_key=lbc_hmac_key, secret=lbc_hmac_secret))
    exchanges.append(exchange.get_exchange(exchange_id='buda'))
    exchanges.append(exchange.get_exchange(exchange_id='binance'))
    # exchanges.append(exchange.get_exchange(exchange_id='poloniex'))
    # exchanges.append(exchange.get_exchange(exchange_id='bitstamp'))
    # exchanges.append(exchange.get_exchange(exchange_id='cex'))
    
    return exchanges


def print_review_body(coin: str, min_ask, max_bid, trm):
    spread = max_bid.usd_price - min_ask.usd_price
    spread_pct = max_bid.usd_price/min_ask.usd_price - 1
    print(f'\nCoin: \t\t{coin}')
    print(f'Min ask:\tUSD {min_ask.usd_price:,.0f} (COP {min_ask.usd_price * trm:,.0f}) at {min_ask.exchange_name.title()}')
    print(f'Max bid:\tUSD {max_bid.usd_price:,.0f} (COP {max_bid.usd_price * trm:,.0f}) at {max_bid.exchange_name.title()}')
    print(f'Spread:\t\tUSD {spread:,.0f} (COP {spread * trm:,.0f}) / {spread_pct:.1%}')
    # print('-' * 43, end='\n\n')


@click.command()
@click.option('--freq', '-f', default=5, help='Frequency in minutes for checking the spread')
@click.option('--spread-threshold', '-s', default=12, help=r'Minimum % of spread to notify')
def main(freq, spread_threshold):
    print('\n*** Crypto monitor running ***\n')
    
    date1 = datetime.today().date()
    # date = time.strftime('%Y-%m-%d')
    # pwd = input(f'Type your password for {sender_email} and press enter: ')
    pwd = secrets.keys('sender password')
    # trm = TrmSoapClient.trm(date)['value']
    trm = utils.get_trm()
    print(f'TRM for today is {trm:,.2f}\n')
    
    exchanges = get_exchanges()
    bids = []
    asks = []
    while True:
        if datetime.today().date() > date1:
            trm = utils.get_trm()
            date1 = datetime.today().date()

        print_review_hdr()
        for coin in ['BTC', 'ETH', 'BCH', 'LTC']:
            for ex in exchanges:
                bid = ex.get_bid(coin, trm)
                ask = ex.get_ask(coin, trm)
                if not bid is None: bids.append(bid)
                if not ask is None: asks.append(ask)
                
            max_bid = max(bids)
            min_ask = min(asks)
            # spread = max_bid.usd_price - min_ask.usd_price
            spread_pct = max_bid.usd_price/min_ask.usd_price - 1
        
            print_review_body(coin, min_ask, max_bid, trm)

            if max_bid.exchange_name != min_ask.exchange_name and spread_pct * 100 > spread_threshold:
                msg = get_alert_msg(max_bid, min_ask, trm)
                # print(msg)
                playsound('zapsplat.mp3')
                print('A new spread alert has been sent to ', sender_email)
                subject = f'Subject: Spread alert on {coin} ({spread_pct:,.1%})\n\n'
                msg = subject + msg
                utils.send_email(sender_email, receiver_email, pwd, msg)

            bids.clear()
            asks.clear()
        time.sleep(freq * 60)
        

if __name__ == '__main__':
    # print(get_trm())
    main()
