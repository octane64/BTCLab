from dataclasses import dataclass
from retry import retry
import requests


@dataclass
class TelegramBot():
    bot_token: str
    chat_id: str

    @retry(ConnectionError, tries=5, delay=10, backoff=2)
    def send_msg(self, msg):
        url = f'https://api.telegram.org/bot{self.bot_token}/sendMessage?chat_id={self.chat_id}&text={msg}'
        requests.get(url) #TODO Check response and log when not OK
        # When using someone else chat bot, response is:
        # {"ok":false,"error_code":400,"description":"Bad Request: chat not found"}
