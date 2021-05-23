import yaml
import requests
from requests.exceptions import ConnectionError
import smtplib, ssl
from retry import retry

port = 587  # For starttls
smtp_server = 'smtp.gmail.com'

def send_email(sender_email, receiver_email, pwd, msg):
    context = ssl.create_default_context()
    with smtplib.SMTP(smtp_server, port) as server:
        server.ehlo()  # Can be omitted
        server.starttls(context=context)
        server.ehlo()  # Can be omitted
        server.login(sender_email, pwd)
        server.sendmail(sender_email, receiver_email, msg)


@retry(ConnectionError, tries=5, delay=10, backoff=2)
def send_msg(telegram_bot_token, telegram_chat_id, msg):
    url = f'https://api.telegram.org/bot{telegram_bot_token}/sendMessage?chat_id={telegram_chat_id}&text={msg}'
    requests.get(url)


def get_config(file_name="./btclab/config.yaml") -> dict:
    to_ret = None
    with open(file_name, "r") as stream:
        try:
            to_ret = yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            print(exc)
    return to_ret
