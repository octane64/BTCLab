from dataclasses import dataclass, field
from lbcapi3 import api
import ccxt
import backoff
import operator
import secrets
from textwrap import dedent


trading_fees = {'buda': 0.04, 'binance': 0.01}


@dataclass
class Profile:
    username: str
    feedback_score: int
    trade_count: str
    name: str


@dataclass
class Order():
    id: str
    ticker: str
    operation: str
    exchange_name: str
    price: float
    currency: float
    usd_price: float
    amount: float
    min_amount: float
    BID = 'bid'
    ASK = 'ask'

    # def get_link_to_add(self):
    #     pass

    def __eq__(self, other):
        return self.usd_price == other.usd_price
 
    def __lt__(self, other):
        return self.usd_price < other.usd_price
    
    def __le__(self, other):
        return self.usd_price <= other.usd_price

    def __gt__(self, other):
        return self.usd_price > other.usd_price
    
    def __ge__(self, other):
        return self.usd_price >= other.usd_price


@dataclass
class LocalBitcoinOrder(Order):
    bank_name: float
    msg: str
    profile: Profile

    def get_link_to_add(self):
        return 'https://localbitcoins.com/ad/' + self.id

    def __str__(self):
        s = f'''
            Seller:\t\t{self.profile.name}
            Bank:\t\t{self.bank_name}
            Price:\t\t{self.currency} {self.price:,.2f}
            Amount:\t\t${self.min_amount:,.0f} - ${self.amount:,.0f}
            '''
        return dedent(s)


@dataclass
class Exchange():
    id: str
    api_key: str = ''
    secret: str = ''
    timeout: int = 30000
    

    def __post_init__(self):
        exchange_class = getattr(ccxt, self.id)
        self.connection = exchange_class({
            'apiKey': self.api_key,
            'secret': self.secret,
            'timeout': self.timeout,
            'enableRateLimit': True,
        })

    def _get_symbol(self, coin):
        symbol = ''

        if self.id == 'Kraken':
            symbol = f'{coin}/USDT'
        elif self.id in ('LocalBitcoins', 'buda'):
            symbol = f'{coin}/COP'
        elif self.id == 'bitstamp':
            symbol = f'{coin}/USD'
        else:
            symbol = f'{coin}/USDT'
        
        return symbol


    @backoff.on_exception(backoff.expo, (ccxt.NetworkError, ccxt.ExchangeNotAvailable), max_tries=3, max_time=60*3)
    def _get_order(self, coin: str, operation: str, trm: float) -> Order:
        price_tag = 'ask' if operation == 'buy' else 'bid'
        
        symbol = self._get_symbol(coin)
        ticker = self.connection.fetch_ticker(symbol=symbol) # 'BTC/USDT'
        quote_crncy = symbol[symbol.index('/') + 1:]

        price = float(ticker[price_tag])
        if quote_crncy == 'COP':
            usd_price = price / trm
        else:
            usd_price = price
        # except ccxt.base.errors.NetworkError ne
        
        order = Order(id=ticker['timestamp'], 
                        exchange_name=self.id,
                        ticker=ticker['symbol'],
                        operation=operation,
                        price=price,
                        currency=quote_crncy,
                        usd_price=usd_price,
                        amount=0, 
                        min_amount=0)
        return order


    def get_bid(self, coin: str, trm: float) -> Order:
        return self._get_order(coin, 'sell', trm=trm)
    
    def get_ask(self, coin: str, trm: float) -> Order:
        return self._get_order(coin, 'buy', trm=trm)


@dataclass
class LocalBitcoins(Exchange):
    def __post_init__(self):
        self.connection = api.hmac(self.api_key, self.secret)

    @backoff.on_exception(backoff.expo, ConnectionError , max_tries=3, max_time=60*3)
    def _get_adds(self, coin, bank_list, operation: str):
        # payment_method = 'national-bank-transfer'
        payment_method = 'transfers-with-specific-bank'
        country_code = 'COP'
        end_point = f'/{operation}-bitcoins-online/{country_code}/{payment_method}/.json'
        adds_dic = self.connection.call('GET', end_point).json()
        symbol = super()._get_symbol(coin)

        adds = []
        for add in adds_dic['data']['ad_list']:
            profile = Profile(username=add['data']['profile']['username'],
                                feedback_score=add['data']['profile']['feedback_score'],
                                trade_count=add['data']['profile']['trade_count'],
                                name=add['data']['profile']['name'])
            
            lbc_add = LocalBitcoinOrder(id=str(add['data']['ad_id']),
                                        ticker=symbol,
                                        operation=add['data']['trade_type'],
                                        exchange_name='LocalBitcoins',
                                        currency=add['data']['currency'],
                                        price=float(add['data']['temp_price']),
                                        usd_price=float(add['data']['temp_price_usd']),
                                        min_amount=float(add['data']['min_amount'] or 0),
                                        amount=float(add['data']['max_amount_available'] or 0),
                                        bank_name=add['data']['bank_name'],
                                        msg=add['data']['msg'],
                                        profile=profile)
            
            # if any(bank in lbc_add.bank_name.lower() for bank in bank_list):
            if 'xpay' not in lbc_add.bank_name.lower() and 'fastpayments' not in lbc_add.bank_name.lower():
                if lbc_add.amount >= 1_000_000: adds.append(lbc_add)

        return adds

    def get_bid(self, coin: str, trm: float = 0) -> Order:
        if coin == 'BTC':
            symbol = super()._get_symbol(coin)
            buy_adds = self._get_adds(coin, ['bancolombia', 'nequi'], 'sell')
            sorted_adds = sorted(buy_adds, key=operator.attrgetter('price'))
            bid = sorted_adds[0]
            quote_crncy = symbol[symbol.index('/') + 1:]
            
            if quote_crncy == 'COP' and trm != 0: 
                bid.usd_price = bid.price/trm
        else:
            bid = None
        
        return bid

    def get_ask(self, coin: str, trm: float = 0) -> Order:
        if coin == 'BTC':
            symbol = super()._get_symbol(coin)
            sell_adds = self._get_adds(coin, ['bancolombia', 'nequi'], 'buy')
            sorted_adds = sorted(sell_adds, key=operator.attrgetter('price'))
            ask = sorted_adds[0]
            quote_crncy = symbol[symbol.index('/') + 1:]
            
            if quote_crncy == 'COP' and trm != 0:
                ask.usd_price = ask.price/trm
        else:
            ask = None
        
        return ask


def get_exchange(exchange_id: str, api_key: str = None, secret: str = None) -> Exchange:
    if exchange_id == 'LocalBitcoins':
        return LocalBitcoins(id=exchange_id, api_key=api_key, secret=secret)
    else:
        return Exchange(id=exchange_id, api_key=api_key, secret=secret)


def main():
    lbc_hmac_key = secrets.keys('lbc_hmac_key')
    lbc_hmac_secret = secrets.keys('lbc_hmac_secret')
    lbc = get_exchange('LocalBitcoins', lbc_hmac_key, lbc_hmac_secret)
    ask = lbc.get_ask('BTC')
    print('\nLowest ask in LocalBitcoins:', ask, sep='\n')
    bid = lbc.get_bid('BTC')
    print('\nHighest bid in LocalBitcoins:', bid, sep='\n')
    


if __name__ == '__main__':
    main()
