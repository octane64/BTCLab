import requests
import smtplib, ssl


port = 587  # For starttls
smtp_server = "smtp.gmail.com"


def send_email(sender_email, receiver_email, pwd, msg):
    context = ssl.create_default_context()
    with smtplib.SMTP(smtp_server, port) as server:
        server.ehlo()  # Can be omitted
        server.starttls(context=context)
        server.ehlo()  # Can be omitted
        server.login(sender_email, pwd)
        server.sendmail(sender_email, receiver_email, msg)


def send_msg(telegram_bot_token, chat_id, msg):
    url = f"https://api.telegram.org/bot{telegram_bot_token}/sendMessage?chat_id={chat_id}&text={msg}"

    # send the msg
    requests.get(url)