import pprint
import time
import click
import secrets
from datetime import datetime
import exchange
import utils
from exchange import Order
from playsound import playsound


def print_review_hdr():
    date_and_time = time.strftime('%Y-%m-%d %X')
    s = date_and_time.center(53, '-')
    print('\n\n', s)

@click.command()
@click.option('--freq', '-f', default=5, help='Frequency in minutes for checking the spread')
@click.option('--amount', '-a', default=2000000, help='Amount to invest in COP')
@click.option('--profit-threshold', '-p', default=2, help=r'Minimum % of spread to notify')
def main(freq, amount, profit_threshold):
    receiver_email = "velasquez.gaviria@gmail.com"
    sender_email = secrets.keys('sender email')
    pwd = secrets.keys('sender password')
    date1 = datetime.today().date()
    trm = utils.get_trm()
    buda = exchange.get_exchange('buda')
    binance = exchange.get_exchange('binance')

    lbc_hmac_key = secrets.keys('lbc_hmac_key')
    lbc_hmac_secret = secrets.keys('lbc_hmac_secret')
    lbc = exchange.get_exchange('LocalBitcoins', lbc_hmac_key, lbc_hmac_secret)
    
    buda_trading_fee = 0.004
    binance_trading_fee = 0.001
    data = {}

    print(f'TRM: {trm:,.2f}')
    while True:
        # Update TRM if running for several days
        if datetime.today().date() > date1:
            trm = utils.get_trm()
            date1 = datetime.today().date()
        
        # What to buy and what to sell?
        data.clear()
        for coin in 'BTC ETH BCH LTC'.split():
            binance_ticker = binance.connection.fetch_ticker(symbol=f'{coin}/USDT')
            buda_ticker = buda.connection.fetch_ticker(symbol=f'{coin}/COP')
            ask_price_cop = buda_ticker['ask']
            bid_price_cop = binance_ticker['bid'] * trm
            spread_pct = round((bid_price_cop/ask_price_cop - 1) * 100, 1)
            data[coin] = {
                            'coin': coin, 
                            'bid': bid_price_cop, 
                            'ask': ask_price_cop, 
                            'spread pct': spread_pct
                         }

        coin_with_max_spread = max(data.values(), key=lambda v: v['spread pct'])['coin']
        coin_with_min_spread = min(data.values(), key=lambda v: v['spread pct'])['coin']

        print_review_hdr()

        max_spread = data[coin_with_max_spread]['spread pct']
        min_spread = data[coin_with_min_spread]['spread pct']

        msg = f'\nHighest spread is now in {coin_with_max_spread}: {max_spread}%'
        msg += f'\nLowest spread is now in  {coin_with_min_spread}: {min_spread}%'

        # Buy coins in Buda
        pair1 = data[coin_with_max_spread]['coin'] + '/COP'
        pair1_ask_price = buda.connection.fetch_ticker(symbol=pair1)['ask']
        pair1_bid_price = buda.connection.fetch_ticker(symbol=pair1)['bid']
        pair1_price = (pair1_ask_price + pair1_bid_price) / 1.75
        pair1_net_qty = amount / pair1_price * (1 - buda_trading_fee)
        
        # If coin to buy is BTC check whether it's cheaper on LBC
        if coin_with_max_spread == 'BTC':
            lbc_ask = lbc.get_ask('BTC').price
            if lbc_ask < pair1_price:
                pair1_net_qty = amount / lbc_ask
                msg += f'\n\nBuy {pair1_net_qty:.6f} {coin_with_max_spread}/COP @ {lbc_ask:,.0f} in LBC'
            else:
                msg += f'\n\nBuy {pair1_net_qty:.6f} {coin_with_max_spread}/COP @ {lbc_ask:,.0f} in Buda'

        # Use BTC as bridge coin to buy the coin with the lowest spread
        if coin_with_max_spread != 'BTC':
            # We have to sell the alt coin for BTC. The coin with the 
            # minimum spread will be bought later with those BTCs
            temp_pair = f'{coin_with_max_spread}/BTC'
            temp_pair_price = binance.connection.fetch_ticker(symbol=temp_pair)['bid']
            temp_pair_net_qty = pair1_net_qty * temp_pair_price * (1 - binance_trading_fee)
            pair1_net_qty = temp_pair_net_qty
            msg += f'\nSell {temp_pair} to get {temp_pair_net_qty:,.6f} BTC ({temp_pair}: {temp_pair_price:,.6f})'
        else:
            temp_pair_net_qty = pair1_net_qty

        
        # Buy coin with the lowest spread
        pair2 = f'{coin_with_min_spread}/BTC'
        if pair1[:3] == pair2[-3:]:
            time.sleep(freq * 60)
            continue
        
        pair2_price = binance.connection.fetch_ticker(symbol=pair2)['ask']
        pair2_net_qty = pair1_net_qty / pair2_price * (1 - binance_trading_fee)
        msg += f'\nBuy {pair2_net_qty:,.6f} {pair2} @ {pair2_price:,.6f}'

        # Sell @ Binance for coin with min spread
        # TODO deduct withdrawal fee

        # Withdrawal to Buda and sell for COP
        # TODO deduct withdrawal fee
        pair3 = f'{coin_with_min_spread}/COP'.upper()
        pair3_price_bid = buda.connection.fetch_ticker(symbol=pair3)['bid']
        pair3_price_ask = buda.connection.fetch_ticker(symbol=pair3)['ask']
        pair3_price = pair3_price_bid + ((pair3_price_ask - pair3_price_bid) / 4)
        pair3_net_qty = pair3_price * pair2_net_qty * (1 - buda_trading_fee)
        msg += f'\nSell {pair2_net_qty:,.6f} {pair3} @ {pair3_price:,.0f}'

        profit = pair3_net_qty - amount
        return_pct = pair3_net_qty / (amount) - 1
        msg += f'\n\nFor ${amount:,.0f} invested, profit is ${profit:,.2f} ({return_pct:.2%})'

        print(msg)

        if return_pct * 100 > profit_threshold: 
            playsound('zapsplat.mp3')
            subject = f'Subject: {return_pct:.2%} with {coin_with_max_spread} and {coin_with_min_spread}\n\n'
            email_msg = subject + msg
            utils.send_email(sender_email, receiver_email, pwd, email_msg)

        time.sleep(freq * 60)


if __name__ == "__main__":
    main()