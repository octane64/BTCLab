from suds.client import Client
import time


WSDL_URL = 'https://www.superfinanciera.gov.co/SuperfinancieraWebServiceTRM/TCRMServicesWebService/TCRMServicesWebService?WSDL'
date = time.strftime('%Y-%m-%d')

def trm(date):
    try:
        client = Client(WSDL_URL, location=WSDL_URL, faults=True)
        trm =  client.service.queryTCRM(date)
        trm_dict = Client.dict(trm)
    except Exception as e:
        return str(e)

    return trm_dict


if __name__ == "__main__":
    print(trm(date))
