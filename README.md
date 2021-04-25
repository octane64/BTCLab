# BTCLab
A bot for Crypto orders management

# Set-up process

## Clone repo
```sh
$ git clone https://github.com/octane64/BTCLab.git
$ cd BTCLab
$ (mac || windows) python -m venv env || (linux) virtualenv env
$ source env/bin/activate || (windows) source env/Scripts/activate
```
## Install project packages
```sh
$ pip install -r requirements.txt
```
## Configure the program
There is a `config.yaml` file at the root level directory with the following parameters for you to customize the program execution/decision making process:
- **Bot**
    - `dummy_mode`: A value of true indicates that orders will be 'dummy' (your balance on **binance** will not be affected). A value of false indicates otherwise.
    - `frequency`: Minutes to wait between bot cycles
    - `insufficient_funds_wait_minutes`: Minutes to wait before the next cycle when insufficient funds to place an order
    - `min_drop`: Percentage value _(0-100)_ for the **minimun drop** for an order to be considered
    - `min_discount`: Percentage value _(0-100)_ for successive potential orders to be considered
    - `tickers`: A list of the **symbols/tickers** that you want the bot to track and consider. E.g:
        - BTC
        - ETH
        - DOT
        - XMR
        - BCH
- **Binance:** Parameters to exchange information with the **Binance API**
    - `secret_key`: Secret **API** key
    - `public_key`: Public **API** key
- **Telegram:** Parameters for the program to send notifications via **Telegram's bots**
    - `bot_token`: **Telegram's** bot token
    - `chat_id`: **Telegram's** chat id (recipient)

# Run the program
To run the program, just type the following command and press enter:
```sh
$ python dip_buyer.py
```
# Dependency platforms
## Binance API
This program exchanges information/data using the **Binance API**.  
If you don't have experience with **Binance API**, please refer to their documentation which you can find [here](https://www.binance.com/en/support/faq/c-6).

<a href="http://www.binance.com" target="_blank">
    <img src="https://public.bnbstatic.com/static/images/common/ogImage.jpg" alt="binance" width="200"/>
</a>

## Telegram Notifications (Via Bots)
This program uses **Telegram's bots** to send notifications related with its execution and/or decision making process.  
For this program to be able to notify you via Telegram you will need:  

- A **bot authorization token**
- A **chat id**

If you don't have experience with **Telegram's bots**, please refer to their documentation which you can find [here](https://core.telegram.org/bots).

<a href="http://www.telegram.com" target="_blank">
    <img src="https://i.blogs.es/a1f566/telegram-hero/450_1000.jpg" alt="telegram" width="200"/>
</a>