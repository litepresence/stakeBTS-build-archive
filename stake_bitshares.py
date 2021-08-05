"""
BitShares.org StakeMachine
Interest Payments on Staking
BitShares Management Group Co. Ltd.
"""
# DISABLE SELECT PYLINT TESTS
# pylint: disable=broad-except, bare-except, bad-continuation

# STANDARD IMPORTS
import time
from getpass import getpass
from sqlite3 import connect as sql
from json import loads as json_loads

# PYBITSHARES IMPORTS
from bitshares.account import Account
from bitshares.asset import Asset
from bitshares.bitshares import BitShares
from bitshares.block import Block
from bitshares.instance import set_shared_bitshares_instance
from bitshares.memo import Memo

# BITTREX API IMPORTS
from bittrex_api import Bittrex

# USER DEFINED CONSTANTS
DB = "stake_bitshares.db"
NODE = "wss://node.market.rudex.org"
INTEREST = 0.08
PENALTY = 0.15
STAKE_LENGTH = {
    "invalid": None,
    "stop": 0,
    "three_months": 3,
    "six_months": 6,
    "twelve_months": 12,
}
INVEST_AMOUNTS = [
    25000,
    50000,
    100000,
    250000,
    500000,
    1000000,
    2500000,
    5000000,
    10000000,
]

# RPC TO BITSHARES NODE

def pybitshares_reconnect():
    """
    create locked owner and memo instances of the pybitshares wallet
    """
    bitshares = BitShares(node=NODE, nobroadcast=False)
    set_shared_bitshares_instance(bitshares)
    memo = Memo(blockchain_instance=bitshares)

    return bitshares, memo

# MaKE PAYMENTS

def send_receipt(client, memo, keys):
    """
    send client one BTS with memo to confirm new stake from pybitshares wallet
    """
    try:
        bitshares, _ = pybitshares_reconnect()
        bitshares.wallet.unlock(keys["password"])
        msg = bitshares.transfer(client, 1, "BTS", memo, account=keys["broker"])
        bitshares.wallet.lock()
        bitshares.clear_cache()
    except Exception as error:
        msg = (
            f"pybitshares failed to send receipt to client {client} with memo {memo}, "
            + f"due to {error}"
        )
    return msg


def bittrex_withdrawal(amount, client, keys):
    """
    send funds using the bittrex api
    """
    try:
        bittrex_api = Bittrex(api_key=keys["api_key"], api_secret=keys["api_secret"])
        params = {
            "currencySymbol": "BTS",
            "quantity": str(float(amount)),
            "cryptoAddress": str(client),
        }
        msg = bittrex_api.post_withdrawal(**params)
    except Exception as error:
        msg = f"bittrex failed to send {amount} to client {client}, due to {error}"
    return msg

# DATABASE RECEIPTS

def update_receipt_database(nonce, msg):
    """
    upon every audit worthy event update the receipt database with
    the event millesecond timestamp and a pertinent message
    """
    con = sql(DB)
    cur = con.cursor()
    now = int(1000 * time.time())
    query = f"INSERT INTO receipts (nonce, now, msg) VALUES ({nonce},{now},{msg})"
    cur.execute(query)
    con.commit()
    con.close()

# START AND STOP STAKES

def new_stake(nonce, block, client, amount, months, keys):
    """
    upon receiving a new stake, send receipt to new client and
    insert into database new payouts due; contract, principal, penalty, and interest

    client      - the Bitshares username
    token       - the Bitshares token
    amount      - the amount staked
    payment     - principal, interest, penalty, contract_3, contract_6, or contract_12
    start       - unix when this contract began
    due         - unix when the payment is due
    processed   - unix when the payment was processed
    status      - pending, paid, premature, aborted
    """
    # send confirmation receipt to client with memo using pybitshares
    memo = f"{months} stake contract for {amount} BTS received timestamp {nonce}"
    msg = send_receipt(client, memo, keys)
    update_receipt_database(nonce, msg)
    # open the database
    con = sql(DB)
    cur = con.cursor()
    # insert the contract into the stakes database
    query = (
        "INSERT INTO stakes "
        + "(client, token, amount, type, start, due, processed, status, block) "
        + "VALUES "
        + f"({client}, BTS, 1, contract_{months}, {nonce}, {nonce}, {nonce}, paid, "
        + f"{block}) "
    )
    cur.execute(query)
    # insert the principal into the stakes database
    due = nonce + 86400 * 30 * months
    query = (
        "INSERT INTO stakes "
        + "(client, token, amount, type, start, due, processed, status, block) "
        + "VALUES "
        + f"({client}, BTS, {amount}, principal, {nonce}, {due}, 0, pending), "
        + f"{block}) "
    )
    cur.execute(query)
    # insert the early exit penalty into the stakes database
    penalty = -1 * amount * PENALTY
    query = (
        "INSERT INTO stakes "
        + "(client, token, amount, type, start, due, processed, status, block) "
        + "VALUES "
        + f"({client}, BTS, {penalty}, penalty, {nonce}, {due}, 0, pending, "
        + f"{block}) "
    )
    cur.execute(query)
    # insert the interest payments into the stakes database
    interest = amount * INTEREST
    for month in range(months):
        due = nonce + 86400 * 30 * (1 + month)
        query = (
            "INSERT INTO stakes "
            + "(client, token, amount, type, start, due, processed, status, block) "
            + "VALUES "
            + f"({client}, BTS, {interest}, interest, {nonce}, {due}, 0, pending, "
            + f"{block}) "
        )
        cur.execute(query)
    # commit and close database connection
    con.commit()
    con.close()


def end_stake_prematurely(nonce, block, client, keys):
    """
    send principal less penalty from bittrex
    update database with principal and penalty paid; outstanding interest aborted
    """
    # open db connection and query principal and and penalties due to client
    con = sql(DB)
    cur = con.cursor()
    query = (
        f"SELECT amount FROM stakes WHERE client={client} "
        + "AND (type=principal OR type=penalty)"
    )
    cur.execute(query)
    amount = sum(cur.fetchall())
    # send premature payment to client
    msg = bittrex_withdrawal(amount, client, keys)
    update_receipt_database(nonce, msg)
    # update stakes database for principal, penalties, and interest payments
    # with new status, time processed, and block number
    query = (
        f"UPDATE stakes WHERE "
        + f"client={client} AND status=pending AND type=principal "
        + f"SET status=premature, processed={nonce}, block={block}"
    )
    cur.execute(query)
    query = (
        f"UPDATE stakes WHERE "
        + f"client={client} AND status=pending AND type=penalty"
        + f"SET status=paid, processed={nonce}, block={block}"
    )
    cur.execute(query)
    query = (
        f"UPDATE stakes WHERE "
        + f"client={client} AND status=pending AND type=interest "
        + f"SET status=aborted, processed={nonce}, block={block}"
    )
    cur.execute(query)
    # commit and close database connection
    con.commit()
    con.close()

# CHECK BLOCKS

def get_block_num_current():
    """
    connect to node and get the irreversible block number
    """
    bitshares, _ = pybitshares_reconnect()
    return bitshares.rpc.get_dynamic_global_properties()["last_irreversible_block_num"]


def check_block(block_num, block, keys):
    """
    check for client transfers to the broker in this block
    """

    def get_json_memo(keys, trx):
        """
        using the memo key, decrypt the memo in the client's deposit
        """
        length_of_stake = "invalid"
        try:
            _, memo = pybitshares_reconnect()
            memo.blockchain.wallet.unlock(keys["password"])
            decrypted_memo = memo.decrypt(trx[1]["memo"])
            memo.blockchain.wallet.lock()
            length_of_stake = json_loads(decrypted_memo)["type"].lower()
        except:
            pass
        return length_of_stake

    for trxs in block["transactions"]:
        for _, trx in enumerate(trxs["operations"]):
            # if its a withdrawal to the broker managed account
            if (
                trx[0] == 0
                and Account(trx[1]["to"]).name == keys["broker"]
                and str(trx[1]["amount"]["asset_id"]) == "1.3.0"
            ):
                nonce = int(1000 * time.time())
                client = Account(trx[1]["from"]).name
                amount = int(trx[1]["amount"]["amount"]) / (
                    10 ** Asset("1.3.0").precision
                )
                months = None
                try:
                    months = STAKE_LENGTH[get_json_memo(keys, trx)]
                except:
                    pass
                if months is None:
                    msg = (
                        f"received {amount} from {client} in {block_num} "
                        + "with invalid memo"
                    )
                elif amount not in INVEST_AMOUNTS:
                    msg = (
                        f"received invalid amount {amount} from {client} "
                        + f"in {block_num} with memo {months}"
                    )
                elif months == 0:
                    msg = f"received stop demand from {client} in {block_num}"
                    end_stake_prematurely(nonce, block, client, keys)
                else:
                    msg = (
                        f"received new stake from {client} in {block_num} "
                        + f"for {months} months"
                    )
                    new_stake(nonce, block, client, amount, months, keys)
                update_receipt_database(nonce, msg)

# PRIMARY EVENT BACKBONE

def login():
    """
    user input login credentials for pybitshares and bittrex
    """

    def authenticate(keys):
        """
        make authenticated request to pybitshares wallet and bittrex to test login
        """
        bitshares, _ = pybitshares_reconnect()
        try:
            bitshares.wallet.unlock(keys["password"])
        except:
            pass
        bitshares_auth = bitshares.wallet.locked()
        bitshares.wallet.lock()

        bittrex_auth = False
        try:
            bittrex_api = Bittrex(api_key=keys["api_key"], api_secret=keys["api_secret"])
            msg = bittrex_api.get_balances()
            bts_balance = [i for i in msg if i['currencySymbol'] == 'BTS']
            bittrex_auth = True
        except:
            continue
        return bithares_auth and bittrex_auth


    keys = {}
    authenticated = False
    while not authenticated:
        keys = {
            "broker": input("\nInput BitShares Username and press ENTER:\n"),
            "password": getpass("\nInput Pybitshares Password and press ENTER:\n"),
            "api_key": getpass("\nInput Bittrex API Key and press ENTER:\n"),
            "api_secret": getpass("\nInput Bittrex API Secret and press ENTER:\n"),
        }
        authenticated = authenticate(keys)

    print("AUTHENTICATED")
    time.sleep(3)
    print("\033c")
    return keys


def listener(keys):
    """
    get the last block number checked from the database
    and the latest block number from the node
    check each block in between for stake related transfers from clients
    then update the last block checked in the database
    """

    def get_block_num_database():
        """
        what is the last block number checked in the database?
        """
        con = sql(DB)
        cur = con.cursor()
        query = "SELECT block FROM block"
        cur.execute(query)
        block_num = int(cur.fetchall()[0])
        con.close()
        return block_num

    def set_block_num_database(block_num):
        """
        update the block number last checked in the database
        """
        con = sql(DB)
        cur = con.cursor()
        query = f"UPDATE block SET block={block_num}"
        cur.execute(query)
        con.commit()
        con.close()

    block_last = get_block_num_database()
    block_new = get_block_num_current()
    for block_num in range(block_last + 1, block_new + 1):
        print("\033c")
        print(block_num)
        block = Block(block_num)
        Block.clear_cache()
        check_block(block_num, block, keys)
    set_block_num_database(block_new)


def make_payouts(keys):
    """
    make all interest and principal payments due
    mark interest and principal paid in database
    mark penalties due as aborted in database
    set processed time and block to current for all
    send payments via bittrex api
    """
    block = get_block_num_current()
    now = int(1000 * time.time())
    con = sql(DB)
    cur = con.cursor()
    # gather list of payments due
    query = (
        "SELECT (amount, client, start) FROM stakes "
        + f"WHERE nonce<{now} AND (type=principal OR type=interest)"
    )
    cur.execute(query)
    payments_due = cur.fetchall()
    # update due payments status
    query = (
        f"UPDATE stakes WHERE nonce<{now} AND (type=principal OR type=interest) "
        + f"SET (status=paid, block={block}, processed={now})"
    )
    cur.execute(query)
    query = (
        f"UPDATE stakes WHERE nonce<{now} AND type=penalty "
        + f"SET (status=aborted, block={block}, processed={now})"
    )
    cur.execute(query)
    # commit and close database
    con.commit()
    con.close()
    # make payments
    for payment in payments_due:
        amount = payment[0]
        client = payment[1]
        nonce = payment[2]
        msg = bittrex_withdrawal(amount, client, keys)
        update_receipt_database(nonce, msg)


def main():
    """
    login then begin while loop listening for client requests and making timely payouts
    """
    keys = login()
    while True:
        listener(keys)
        make_payouts(keys)


if __name__ == "__main__":

    main()
