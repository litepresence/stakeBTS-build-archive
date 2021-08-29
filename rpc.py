"""
BitShares.org StakeMachine
Remote Procedure Calls to BitShares Node and Bittrex API
BitShares Management Group Co. Ltd.
"""
# DISABLE SELECT PYLINT TESTS
# pylint: disable=broad-except

# STANDARD PYTHON MODULES
import time
from json import dumps as json_dumps

# PYBITSHARES MODULES
from bitshares.account import Account
from bitshares.bitshares import BitShares
from bitshares.instance import set_shared_bitshares_instance
from bitshares.memo import Memo

# BITTREX MODULES
from bittrex_api import Bittrex
# STAKE BTS MODULES
from config import BROKER, DEV, NODE
from utilities import exception_handler, it, line_info

NINES = 999999999

# CONNECT WALLET TO BITSHARES NODE
def pybitshares_reconnect():
    """
    create locked owner and memo instances of the pybitshares wallet
    :return: two pybitshares instances
    """
    pause = 0
    while True:
        try:
            bitshares = BitShares(node=NODE, nobroadcast=False)
            set_shared_bitshares_instance(bitshares)
            memo = Memo(blockchain_instance=bitshares)
            return bitshares, memo
        except Exception as error:
            print(exception_handler(error), line_info())
            time.sleep(0.1 * 2 ** pause)
            if pause < 13:  # oddly works out to about 13 minutes
                pause += 1
            continue


# RPC BLOCK NUMBER
def get_block_num_current():
    """
    connect to node and get the irreversible block number
    :return int(): block number
    """
    bitshares, _ = pybitshares_reconnect()
    return bitshares.rpc.get_dynamic_global_properties()["last_irreversible_block_num"]


# RPC POST WITHDRAWALS
def post_withdrawal_bittrex(amount, client, api, keys):
    """
    send funds using the bittrex api
    :param int(amount): quantity to be withdrawn
    :param str(client): bitshares username to send to
    :param dict(keys): api keys and secrets for bittrex accounts
    :param int(api): 1, 2, or 3; corporate account to send from
    :return str(msg): withdrawal response from bittrex
    """
    amount = int(amount)
    msg = f"POST WITHDRAWAL BITTREX {amount} {client} {api}, response: "
    print(it("yellow", msg))
    if not DEV:
        try:
            if amount <= 0:
                raise ValueError(f"Invalid Withdrawal Amount {amount}")
            bittrex_api = Bittrex(
                api_key=keys[f"api_{api}_key"], api_secret=keys[f"api_{api}_secret"]
            )
            params = {
                "currencySymbol": "BTS",
                "quantity": str(float(amount)),
                "cryptoAddress": str(client),
            }
            # returns response.json() as dict or list python object
            ret = bittrex_api.post_withdrawal(**params)
            msg += json_dumps(ret)
            if isinstance(ret, dict):
                if "code" in ret:
                    print(it("red", ret), line_info())
                    raise TypeError("Bittrex failed with response code")
        except Exception as error:
            msg += line_info() + " " + exception_handler(error)
            msg += it("red", f"bittrex failed to send {amount} to client {client}",)
            print(msg)
    return msg


def post_withdrawal_pybitshares(amount, client, memo, keys):
    """
    send BTS with memo to confirm new stake from pybitshares wallet
    :param int(amount): quantity to be withdrawn
    :param str(client): bitshares username to send to
    :param dict(keys): contains pybitshares wallet password for corporate account
    :param str(memo): message to client
    :return str(msg): withdrawal response from pybitshares wallet
    """
    amount = int(amount)
    msg = f"POST WITHDRAWAL PYBITSHARES {amount} {client} {memo}, response: "
    print(it("yellow", msg))
    if not DEV:
        try:
            if amount <= 0:
                raise ValueError(f"Invalid Withdrawal Amount {amount}")
            bitshares, _ = pybitshares_reconnect()
            bitshares.wallet.unlock(keys["password"])
            msg += json_dumps(
                bitshares.transfer(client, amount, "BTS", memo, account=keys["broker"])
            )  # returns dict
            bitshares.wallet.lock()
            bitshares.clear_cache()
        except Exception as error:
            msg += line_info() + " " + exception_handler(error)
            msg += it(
                "red",
                f"pybitshares failed to send {amount}"
                + f"to client {client} with memo {memo}, ",
            )
            print(msg)
    return msg


# RPC GET BALANCES
def get_balance_bittrex(keys):
    """
    get bittrex BTS balances for all three corporate accounts
    :param keys: dict containing api keys and secrets for 3 accounts
    :return dict(balances):format {1: 0, 2: 0, 3: 0} with int() BTS balance for each api
    """
    balances = {1: NINES, 2: NINES, 3: NINES}
    if not DEV:
        for api in range(1, 4):
            balance = 0
            try:
                bittrex_api = Bittrex(
                    api_key=keys[f"api_{api}_key"], api_secret=keys[f"api_{api}_secret"]
                )
                # returns list() on success or dict() on error
                ret = bittrex_api.get_balances()
                if isinstance(ret, dict):
                    print(it("red", ret), line_info())
                # ret balance will be strigified float; int(float(()) to return integer
                balance = int(
                    float(
                        [i for i in ret if i["currencySymbol"] == "BTS"][0]["available"]
                    )
                )
            except Exception as error:
                print(exception_handler(error), line_info())
            balances[api] = balance
    print("bittrex balances:", balances)
    return balances


def get_balance_pybitshares():
    """
    get the broker's BTS balance
    :return int(): BTS balance
    """
    try:
        if DEV:
            balance = NINES
        else:
            _, _ = pybitshares_reconnect()
            account = Account(BROKER)
            balance = int(account.balance("BTS")["amount"])
    except Exception as error:
        balance = 0
        print(exception_handler(error), line_info())
    print("pybitshares balance:", balance)
    return balance


def authenticate(keys):
    """
    make authenticated request to pybitshares wallet and bittrex to test login
    :param dict(keys): bittrex api keys and pybitshares wallet password
    :return bool(): do all secrets and passwords authenticate?
    """
    bitshares, _ = pybitshares_reconnect()
    try:
        bitshares.wallet.unlock(keys["password"])
    except Exception:
        pass
    bitshares_auth = bitshares.wallet.unlocked()
    if bitshares_auth:
        print("PYBITSHARES WALLET AUTHENTICATED")
    else:
        print("PYBITSHARES WALLET AUTHENTICATION FAILED")
    bitshares.wallet.lock()
    bittrex_auth = {1: False, 2: False, 3: False}
    try:
        for i in range(3):
            api = i + 1
            bittrex_api = Bittrex(
                api_key=keys[f"api_{api}_key"], api_secret=keys[f"api_{api}_secret"]
            )
            ret = bittrex_api.get_balances()
            if isinstance(ret, list):
                bittrex_auth[api] = True
    except Exception:
        pass
    if all(bittrex_auth.values()):
        print("BITTREX API SECRETS AUTHENTICATED:", bittrex_auth)
    else:
        print("BITTREX API SECRETS FAILED:", bittrex_auth)
    return bitshares_auth and all(bittrex_auth.values())
