# BTCLab
A bot for buying the dips in the crypto markets

# Set-up process

## Clone repo
```sh
$ git clone https://github.com/octane64/BTCLab.git
$ cd BTCLab
$ python -m venv env
$ source env/bin/activate (or $ .\env\Scripts\activate if you are in Windows)
$ pip install -r requirements.txt
$ python btclab/buydips.py --help
```
## Configure the program
There is a `config.yaml` file in the btclab directory with many parameters for you to customize the program execution/decision making process.

IMPORTANT: Tell Git to ignore changes in config.yaml after you've saved the file with your data to prevent your local changes from being uploaded
```sh
$ git update-index --assume-unchanged btclab/config.yaml
``` 

## Setup credentials for Binance
Add BINANCE_API_KEY and BINANCE_API_SECRET with your credentials to access the Binance API as environment variables to your system


# Run the program
To run the program, just type the following command and press enter:
```sh
$ python btclab/buydips.py
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

Add TELEGRAM_BOT_TOKEN as environment variable to your system to authenticate with the Telegram API

If you don't have experience with **Telegram's bots**, please refer to their documentation which you can find [here](https://core.telegram.org/bots).

<a href="http://www.telegram.com" target="_blank">
    <img src="https://i.blogs.es/a1f566/telegram-hero/450_1000.jpg" alt="telegram" width="200"/>
</a>
