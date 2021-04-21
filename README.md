# BTCLab
A bot for Crypto orders management

# Clone repo
```sh
$ git clone https://github.com/octane64/BTCLab.git
$ cd BTCLab
$ (mac || windows) python -m venv env || (linux) virtualenv env
$ source env/bin/activate || (windows) source env/Scripts/activate
```
# Install project packages
```sh
$ pip install -r requirements.txt

# Configure your secrets file
Add a secrets.py file at the root level directory with the following structure:

keys = {
    'binance_key': 'your_binance_key',
    'binance_secret': 'your_binance_secret',
    'Telegram bot token': 'your_telegram_bot_toker (api key)',
    'Telegram chat id': 'your_telegram_chat_ID'
}