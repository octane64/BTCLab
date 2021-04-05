import pprint
import time
import click
from datetime import datetime
import secrets
import exchange
import utils
import requests
from exchange import Order
from playsound import playsound


def send_msg(msg: str, chat_id: str='322464877'):
    bot_token = '1407296421:AAEU0t_vvkE0Dp2TOWxDVGtBRAtG_TnndLU' #OctaneBot
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage?chat_id={chat_id}&text={msg}"

    # send the msg
    requests.get(url)

def print_review_hdr() -> str:
    date_and_time = time.strftime('%Y-%m-%d %X')
    s = date_and_time.center(53, '-')
    print('\n\n', s)

@click.command()
@click.option('--freq', '-f', default=5, help='Frequency in minutes for checking the spread')
@click.option('--amount', '-a', default=2000000, help='Amount to invest in COP')
@click.option('--profit-threshold', '-p', default=3, help=r'Minimum % of profit to notify')
def main(freq, amount, profit_threshold):
    sender_email = "jcvelasquez903@gmail.com"
    receiver_email = "velasquez.gaviria@gmail.com"
    pwd = 'Piramid3'
    buda = exchange.get_exchange('buda')
    lbc_hmac_key = secrets.keys('lbc_hmac_key')
    lbc_hmac_secret = secrets.keys('lbc_hmac_secret')
    lbc = exchange.get_exchange('LocalBitcoins', lbc_hmac_key, lbc_hmac_secret)
    buda_trading_fee_pct = 0.004
    buda_deposit_fee_cop = 6500
    # buda_withdrawal_fee_pct = 0.004
    # buda_withdrawal_fee_cop = 6500

    while True:
        lbc_offer = lbc.get_ask('BTC')
        ask = lbc_offer.price
        bid = buda.connection.fetch_ticker(symbol=f'BTC/COP')['bid']
        # spread_pct = bid/ask - 1

        print_review_hdr()
        amount_to_buy_btc = (amount - buda_deposit_fee_cop) / ask
        msg = f'\n\nBuy {amount_to_buy_btc:.6f} BTC @ ${ask:,.0f} in LocalBitcoins'
        msg += f'\nIn Buda, sell your BTC @ ${bid:,.0f}'

        new_balance_cop = amount_to_buy_btc * bid * (1 - buda_trading_fee_pct) - buda_deposit_fee_cop
        profit = new_balance_cop - amount
        return_pct = new_balance_cop / amount - 1
        
        msg += f'\n\nFor ${amount:,.0f} invested, profit is ${profit:,.0f} ({return_pct:.2%})'
        msg += f'\n\nLBC offer link (Ctrl + click):\n{lbc_offer.get_link_to_add()}'

        print(msg)

        if return_pct * 100 > profit_threshold: 
            playsound('zapsplat.mp3')
            subject = f'Subject: {return_pct:.2%} with BTC\n\n'
            email_msg = subject + msg # + f'\n\n{lbc_offer.msg}'
            utils.send_email(sender_email, receiver_email, pwd, email_msg)
            send_msg(msg)
        time.sleep(freq * 60)


if __name__ == "__main__":
    main()