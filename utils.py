import warnings 
warnings.filterwarnings(action='ignore')
import smtplib, ssl
import pandas as pd
from sodapy import Socrata


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

def get_trm():
    with Socrata("www.datos.gov.co", None) as client:
        trm = client.get("mcec-87by", limit=1)[0]['valor']
    return float(trm)


if __name__ == "__main__":
    print(f'\nTRM for today is {get_trm():,.2f}\n')