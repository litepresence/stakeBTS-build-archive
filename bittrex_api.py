"""
Bittrex Authenticated Ops

Forked:
    https://github.com/jchysk/python-bittrex-v3-sdk/blob/master/client.py

Consulted:
    https://github.com/mkuenzie/bittrex/blob/master/bittrex/bittrex.py
    https://github.com/DevSecNinja/aiobittrexapi/blob/main/aiobittrexapi/utils.py

Added:
    post_withdrawal()
    unit_test()

Passes:
    pylint/black/isort/sourcery

wtfpl litepresence2021
"""

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import requests

API_URL = "https://api.bittrex.com/v3/"
API_KEY = ""  # only for unit testing
API_SECRET = ""  # only for unit testing



class Bittrex:
    """
    Client for Bittrex for V3 API
    """

    def __init__(self, api_key, api_secret):
        self.response = ""
        self.api_key = api_key
        self.api_secret = api_secret
        self.session = self._init_session()


    def _init_session(self):
        header = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        session = requests.session()
        session.headers.update(header)
        return session

    def _request(self, method, endpoint, **kwargs):
        uri = API_URL + endpoint
        self.response = getattr(self.session, method)(uri, **kwargs)
        return self.response.json()

    def _authenticated_request(self, method, endpoint, **kwargs):
        request_data = {}
        payload = ""
        if len(kwargs) > 0:
            if method == "get":
                endpoint = endpoint + "?" + urlencode(kwargs)
            else:
                request_data["data"] = payload = json.dumps(kwargs)

        mill_timestamp = str(int(time.time() * 1000))
        content_hash = hashlib.sha512(payload.encode()).hexdigest()
        uri = API_URL + endpoint
        _pre_sign = mill_timestamp + uri + method.upper() + content_hash

        signature = hmac.new(
            self.api_secret.encode(), _pre_sign.encode(), hashlib.sha512
        ).hexdigest()
        self.session.headers.update(
            {
                "Api-Key": self.api_key,
                "Api-Timestamp": mill_timestamp,
                "Api-Content-Hash": content_hash,
                "Api-Signature": signature,
            }
        )

        self.response = getattr(self.session, method)(uri, **request_data)
        return self.response.json()



    def get_balances(self):
        """
        Used to retrieve all balances from your account.
        :return:
        [
          {
            "currencySymbol": "string",
            "total": "number (double)",
            "available": "number (double)",
            "updatedAt": "string (date-time)"
          }
        ]
        """
        return self._authenticated_request("get", "balances")

    def post_withdrawal(self, **params):

        """
        https://api.bittrex.com/v3/withdrawals
        https://bittrex.github.io/api/v3#/definitions/NewWithdrawal

        @param currencySymbol str(upper) unique symbol of the currency to withdraw from
        @param quantity str(float()) quantity to withdraw
        @param cryptoAddress str() crypto address to withdraw funds to
        @param cryptoAddressTag str() (optional) custom message further specifying how
            to complete the withdrawal (may not be supported for this currency)
        @param clientWithdrawalId: str(uuid) (optional) idempotency client identifier

        :return:
        {
          "id": "string (uuid)",
          "currencySymbol": "string",
          "quantity": "number (double)",
          "cryptoAddress": "string",
          "cryptoAddressTag": "string",
          "txCost": "number (double)",
          "txId": "string",
          "status": "string",
          "createdAt": "string (date-time)",
          "completedAt": "string (date-time)",
          "clientWithdrawalId": "string (uuid)",
          "accountId": "string (uuid)"
        }
        """
        return self._authenticated_request("post", "withdrawals", **params)

    def get_addresses(self):
        '''
        List deposit addresses that have been requested or provisioned
        :return:
        [
          {
            "status": "string",
            "currencySymbol": "string",
            "cryptoAddress": "string",
            "cryptoAddressTag": "string"
          }
        ]
        '''
        return self._authenticated_request("get", "addresses")



def unit_test():
    """
    sample withdrawal operation
    """
    bittrex_api = Bittrex(api_key=API_KEY, api_secret=API_SECRET)

    # POST WITHDRAWAL
    params = {
        "currencySymbol": "BTS",
        "quantity": str(float(100.0)),
        "cryptoAddress": "litepresence1",
        "cryptoAddressTag": "hello world",
    }
    ret = bittrex_api.post_withdrawal(**params)

    print(ret)

    # need to get thailand VPN

if __name__ == "__main__":

    unit_test()
