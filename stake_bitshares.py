"""
BitShares.org StakeMachine
Interest Payments on Staking
BitShares Management Group Co. Ltd.
"""
# DISABLE SELECT PYLINT TESTS
# pylint: disable=broad-except, bare-except, bad-continuation, too-many-branches
# pylint: disable=too-many-statements, too-many-nested-blocks, too-many-arguments
# pylint: disable=too-many-locals

# STANDARD IMPORTS
import time
from copy import deepcopy
from getpass import getpass
from json import loads as json_loads
from sqlite3 import connect as sql
from threading import Thread

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
BROKER = "bitsharesmanagement.group"
MANAGERS = ["dls.cipher", "escrow.zavod.premik"]
BITTREX_1 = ""  # deposit memo account 1
BITTREX_2 = ""  # deposit memo account 2
BITTREX_3 = ""  # deposit memo account 3
INTEREST = 0.08
PENALTY = 0.15
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
# GLOBAL CONSTANTS
MUNIX_MONTH = 86400 * 30 * 1000
TRANSFER_TYPES = {
    "stop"  # client stops all outstanding contracts
    "three_months"  # client creates 3 month contract
    "six_months"  # client creates 6 month contract
    "twelve_months"  # client creates 12 month contract
    "bittrex_to_bmg"  # manager moves funds from bittrex to bitsharemanagment.group
    "bmg_to_bittrex"  # manager moves funds from bitsharemanagment.group to bittrex
    "loan_to_bmg"  # manager makes personal loan to bitsharesmanagement.group
}

MONTHS = {
    "three_months": 3,
    "six_months": 6,
    "twelve_months": 12,
}

# UTILITIES


def munix():
    """
    millesecond unix time stamp
    """
    return int(1000 * time.time())


# CONNECT WALLET TO BITSHARES NODE


def pybitshares_reconnect():
    """
    create locked owner and memo instances of the pybitshares wallet
    """
    bitshares = BitShares(node=NODE, nobroadcast=False)
    set_shared_bitshares_instance(bitshares)
    memo = Memo(blockchain_instance=bitshares)

    return bitshares, memo


# POST WITHDRAWALS


def post_withdrawal_bittrex(amount, client, keys, api):
    """
    send funds using the bittrex api
    :param int(amount): quantity to be withdrawn
    :param str(client): bitshares username to send to
    :param dict(keys): api keys and secrets for bittrex accounts
    :param int(api): 1, 2, or 3; corporate account to send from
    :return str(msg): withdrawal response from bittrex
    """
    try:
        bittrex_api = Bittrex(
            api_key=keys[f"api_{api}_key"], api_secret=keys[f"api_{api}_secret"]
        )
        params = {
            "currencySymbol": "BTS",
            "quantity": str(float(amount)),
            "cryptoAddress": str(client),
        }
        msg = bittrex_api.post_withdrawal(**params)
    except Exception as error:
        msg = f"bittrex failed to send {amount} to client {client}, due to {error}"
    return msg


def post_withdrawal_pybitshares(amount, client, keys, memo):
    """
    send BTS with memo to confirm new stake from pybitshares wallet
    :param int(amount): quantity to be withdrawn
    :param str(client): bitshares username to send to
    :param dict(keys): contains pybitshares wallet password for corporate account
    :param str(memo): message to client
    :return str(msg): withdrawal response from pybitshares wallet
    """
    msg = ""
    try:
        bitshares, _ = pybitshares_reconnect()
        bitshares.wallet.unlock(keys["password"])
        msg += bitshares.transfer(client, amount, "BTS", memo, account=keys["broker"])
        bitshares.wallet.lock()
        bitshares.clear_cache()
    except Exception as error:
        msg += (
            f"pybitshares failed to send receipt for {amount}"
            + f"to client {client} with memo {memo}, "
            + f"due to {error}"
        )
    return msg


# GET BALANCES


def get_balance_bittrex(keys):
    """
    get bittrex BTS balances for all three corporate accounts
    :param keys: dict containing api keys and secrets for 3 accounts
    :return dict(balances):format {1: 0.0, 2: 0.0, 3: 0.0} with BTS balance for each api
    """
    balances = {}
    for api in range(1, 4):
        balance = 0
        try:
            bittrex_api = Bittrex(
                api_key=keys[f"api_{api}_key"], api_secret=keys[f"api_{api}_secret"]
            )
            balance = [
                i for i in bittrex_api.get_balances() if i["currencySymbol"] == "BTS"
            ][0]["available"]
        except:
            pass
        balances[api] = balance
    return balances


def get_balance_pybitsares():
    """
    get the broker's BTS balance
    :return float(): BTS balance
    """
    _, _ = pybitshares_reconnect()
    account = Account(BROKER)
    return account.balance("BTS")["amount"]


# DATABASE RECEIPTS


def update_receipt_database(nonce, msg, con):
    """
    upon every audit worthy event update the receipt database with
    the event millesecond timestamp and a pertinent message
    :param int(nonce): munix timestamp *originally* associated with this stake
    :param str(msg): auditable event documentation
    :return None:
    """

    cur = con.cursor()
    query = "INSERT INTO receipts (nonce, now, msg) VALUES (?,?,?)"
    values = (
        nonce,
        munix(),
        msg,
    )
    cur.execute(query, values)
    # commit the database edit
    con.commit()


# START AND STOP STAKES


def stake_start(nonce, block, client, amount, months, con, keys=None):
    """
    upon receiving a new stake, send receipt to new client and
    insert into database new payouts due, sql columns in stake db:

    client      - the Bitshares username
    token       - the Bitshares token
    amount      - the amount staked
    payment     - principal, interest, penalty, contract_3, contract_6, or contract_12
    start       - unix when this contract began
    due         - unix when the payment is due
    processed   - unix when the payment was processed
    status      - pending, paid, premature, aborted
    number      - the interest payment number, eg 1,2,3; 0 for all other payment types

    :param int(nonce): munix timestamp *originally* associated with this stake
    :param int(block): block number when this stake began
    :param str(client): bitshares username of staking client
    :param int(amount): the amount the client is staking
    :param int(months): the number of months the client is staking
    :param dict(keys): pybitshares wallet password
    :return None:
    """
    if keys is not None:
        # send confirmation receipt to client with memo using pybitshares
        memo = f"{months} stake contract for {amount} BTS received timestamp {nonce}"
        msg = post_withdrawal_pybitshares(1, client, keys, memo)
        update_receipt_database(nonce, msg, con)
    # open the database
    cur = con.cursor()
    # insert the contract into the stakes database
    contract = f"contract_{months}"
    query = (
        "INSERT INTO stakes "
        + "(client, token, amount, type, start, due, processed, status, block, number) "
        + "VALUES (?,?,?,?,?,?,?,?,?,?)"
    )
    values = (
        client,
        "BTS",
        1,
        contract,
        nonce,
        nonce,
        nonce,
        "paid",
        block,
        0,
    )
    cur.execute(query, values)
    # insert the principal into the stakes database
    due = nonce + months * MUNIX_MONTH
    query = (
        "INSERT INTO stakes "
        + "(client, token, amount, type, start, due, processed, status, block, number) "
        + "VALUES (?,?,?,?,?,?,?,?,?,?)"
    )
    values = (
        client,
        "BTS",
        amount,
        "principal",
        nonce,
        due,
        0,
        "pending",
        block,
        0,
    )
    cur.execute(query, values)
    # insert the early exit penalty into the stakes database
    penalty = -1 * amount * PENALTY
    query = (
        "INSERT INTO stakes "
        + "(client, token, amount, type, start, due, processed, status, block, number) "
        + "VALUES (?,?,?,?,?,?,?,?,?,?)"
    )
    values = (
        client,
        "BTS",
        penalty,
        "penalty",
        nonce,
        due,
        0,
        "pending",
        block,
        0,
    )
    cur.execute(query, values)
    # insert the interest payments into the stakes database
    interest = amount * INTEREST
    for month in range(1, months + 1):
        due = nonce + month * MUNIX_MONTH
        query = (
            "INSERT INTO stakes "
            + "(client, token, amount, type, start, due, processed, status, block, "
            + "number) "
            + "VALUES (?,?,?,?,?,?,?,?,?,?)"
        )
        values = (
            client,
            "BTS",
            interest,
            "interest",
            nonce,
            due,
            0,
            "pending",
            block,
            month,
        )
        cur.execute(query, values)
    # commit the database edit
    con.commit()


def stake_stop(nonce, block, client, keys, con):
    """
    send principal less penalty from pybitshares wallet
    update database with principal and penalty paid; outstanding interest aborted

    :param int(nonce): munix timestamp *originally* associated with this stake
    :param int(block): block number when this stake began
    :param str(client): bitshares username of staking client
    :param dict(keys): pybitshares wallet password
    :return None:

    """
    # open db connection and query principal and and penalties due to client
    cur = con.cursor()
    query = (
        "SELECT amount FROM stakes WHERE client=? AND (type=principal OR type=penalty)"
    )
    values = (client,)
    cur.execute(query, values)
    amount = sum(cur.fetchall())
    # send premature payment to client
    memo = f"closing stakeBTS {nonce} prematurely at client request"
    msg = post_withdrawal_pybitshares(amount, client, keys, memo)
    update_receipt_database(nonce, msg, con)
    # update stakes database for principal, penalties, and interest payments
    # with new status, time processed, and block number
    query = (
        "UPDATE stakes WHERE "
        + "client=? AND status=pending AND type=principal "
        + "SET status=premature, processed=?, block=?"
    )
    values = (
        client,
        nonce,
        block,
    )
    cur.execute(query, values)
    query = (
        "UPDATE stakes WHERE "
        + "client=? AND status=pending AND type=penalty"
        + "SET status=paid, processed=?, block=?"
    )
    values = (
        client,
        nonce,
        block,
    )
    cur.execute(query, values)
    query = (
        "UPDATE stakes WHERE "
        + "client=? AND status=pending AND type=interest "
        + "SET status=aborted, processed=?, block=?"
    )
    values = (
        client,
        nonce,
        block,
    )
    cur.execute(query, values)
    # commit the database edit
    con.commit()


# CHECK BLOCKS


def get_block_num_current():
    """
    connect to node and get the irreversible block number
    """
    bitshares, _ = pybitshares_reconnect()
    return bitshares.rpc.get_dynamic_global_properties()["last_irreversible_block_num"]


def check_block(block_num, block, keys, con):
    """
    check for client transfers to the broker in this block

    :param int(block_num): block number associated with this block
    :param dict(block): block data
    :param dict(keys): bittrex api keys and pybitshares wallet password
    :return None:
    """

    def get_json_memo(keys, trx):
        """
        using the memo key, decrypt the memo in the client's deposit
        """
        msg = {"type": "invalid"}
        try:
            _, memo = pybitshares_reconnect()
            memo.blockchain.wallet.unlock(keys["password"])
            decrypted_memo = memo.decrypt(trx[1]["memo"])
            memo.blockchain.wallet.lock()
            msg = json_loads(decrypted_memo)
        except:
            pass
        return msg

    for trxs in block["transactions"]:
        for _, trx in enumerate(trxs["operations"]):
            # if it is a BTS transfer to the broker managed account
            if (
                trx[0] == 0
                and Account(trx[1]["to"]).name == keys["broker"]
                and str(trx[1]["amount"]["asset_id"]) == "1.3.0"
            ):
                # provide timestamp, extract amount and client, dedode the memo
                memo = get_json_memo(keys, trx)
                nonce = munix()
                client = Account(trx[1]["from"]).name
                amount = int(trx[1]["amount"]["amount"]) / (
                    10 ** Asset("1.3.0").precision
                )

                if client not in MANAGERS:
                    # could not decode memo, fine user 50 BTS and refund
                    if memo["type"] == "invalid":
                        msg = (
                            f"received {amount} from {client} in {block_num} "
                            + "with invalid memo, refunding w/ 50 BTS penalty"
                        )
                        amount -= 50
                        if amount > 10:
                            post_withdrawal_pybitshares(int(amount), client, keys, msg)

                    # new client wants to stake and used a valid memo
                    elif memo["type"] in [
                        "three_months",
                        "six_months",
                        "twelve_months",
                    ]:
                        months = MONTHS[memo["type"]]
                        # client sent an invalid amount
                        if amount not in INVEST_AMOUNTS:

                            msg = (
                                f"received invalid amount {amount} from {client} "
                                + f"in {block_num} with memo {memo['type']}"
                            )
                            amount -= 50
                            if amount > 10:
                                post_withdrawal_pybitshares(
                                    int(amount), client, keys, msg
                                )
                        # client sent a valid amount
                        else:
                            msg = (
                                f"received new stake from {client} in {block_num} "
                                + f"for {months} months and {amount} amount"
                            )
                            stake_start(nonce, block, client, amount, months, keys)
                    # existing client wishes to stop all his stake contracts prematurely
                    elif memo["type"] == "stop":
                        msg = f"received stop demand from {client} in {block_num}"
                        stake_stop(nonce, block, client, keys, con)

                if client in MANAGERS:
                    valid = True
                    # the manager wishes to move funds from bittrex to broker
                    if memo["type"] == "bittrex_to_bmg":
                        try:
                            amount = int(memo["amount"])
                            api = int(memo["api"])
                            assert api in [1, 2, 3]
                            assert amount > 1000
                            post_withdrawal_bittrex(amount, client, keys, api)
                        except:
                            valid = False
                    # the manager wishes to move funds from broker to bittrex
                    elif memo["type"] == "bmg_to_bittrex":
                        try:
                            amount = int(memo["amount"])
                            api = int(memo["api"])
                            assert api in [1, 2, 3]
                            assert amount > 1000
                            decode_api = {1: BITTREX_1, 2: BITTREX_2, 3: BITTREX_3}
                            bittrex_memo = decode_api[api]
                            post_withdrawal_pybitshares(
                                int(amount), "bittrex_deposit", keys, bittrex_memo
                            )
                        except:
                            valid = False
                    # the manager has loaned the broker personal funds
                    elif memo["type"] == "loan_to_bmg":
                        try:
                            amount = int(memo["amount"])
                            msg = f"{client} has loaned the broker {amount}"
                        except:
                            valid = False
                    else:
                        valid = False
                    # send a 0.1 bts to the manager with memo declaring invalid request
                    if not valid:
                        amount = 0.1
                        msg = "manager sent an invalid request:" + str(memo)
                        post_withdrawal_pybitshares(amount, client, keys, msg)

                update_receipt_database(nonce, msg, con)


# PRIMARY EVENT BACKBONE


def login():
    """
    user input login credentials for pybitshares and bittrex

    :return dict(keys): authenticated bittrex api keys and pybitshares wallet password
    """

    def authenticate(keys):
        """
        make authenticated request to pybitshares wallet and bittrex to test login

        :param dict(keys): bittrex api keys and pybitshares wallet password
        :return bool(): do all secrets and passwords authenticate?
        """
        bitshares, _ = pybitshares_reconnect()
        try:
            bitshares.wallet.unlock(keys["password"])
        except:
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
        except:
            pass
        if all(bittrex_auth.values()):
            print("BITTREX API SECRETS AUTHENTICATED:", bittrex_auth)
        else:
            print("BITTREX API SECRETS FAILED:", bittrex_auth)

        return bitshares_auth and all(bittrex_auth.values())

    keys = {}
    authenticated = False
    while not authenticated:
        keys = {
            "broker": input("\nInput BitShares Username and press ENTER:\n"),
            "password": getpass("\nInput Pybitshares Password and press ENTER:\n"),
            "api_1_key": getpass("\nInput Bittrex API 1 Key and press ENTER:\n"),
            "api_1_secret": getpass("\nInput Bittrex API 1 Secret and press ENTER:\n"),
            "api_2_key": getpass("\nInput Bittrex API 2 Key and press ENTER:\n"),
            "api_2_secret": getpass("\nInput Bittrex API 2 Secret and press ENTER:\n"),
            "api_3_key": getpass("\nInput Bittrex API 3 Key and press ENTER:\n"),
            "api_3_secret": getpass("\nInput Bittrex API 3 Secret and press ENTER:\n"),
        }
        authenticated = authenticate(keys)

    print("AUTHENTICATED")
    time.sleep(3)
    print("\033c")
    return keys


def listener(keys, con):
    """
    get the last block number checked from the database
    and the latest block number from the node
    check each block in between for stake related transfers from clients
    then update the last block checked in the database

    :param dict(keys): bittrex api keys and pybitshares wallet password
    """

    def get_block_num_database():
        """
        what is the last block number checked in the database?
        """

        cur = con.cursor()
        query = "SELECT block FROM block"
        cur.execute(query)
        block_num = int(cur.fetchall()[0])
        return block_num

    def set_block_num_database(block_num):
        """
        update the block number last checked in the database
        :param int(block_num): the bitshares block number last checked by the bot
        """

        cur = con.cursor()
        query = "UPDATE block SET block=?"
        values = (block_num,)
        cur.execute(query, values)
        # commit the database edit
        con.commit()

    block_last = get_block_num_database()
    block_new = get_block_num_current()
    for block_num in range(block_last + 1, block_new + 1):
        print("\033c")
        print(block_num)
        block = Block(block_num)
        Block.clear_cache()
        check_block(block_num, block, keys, con)
    set_block_num_database(block_new)


def make_payouts(keys, con):
    """
    make all interest and principal payments due
    mark interest and principal paid in database
    mark penalties due as aborted in database
    set processed time and block to current for all
    send payments via pybitshares wallet

    :param dict(keys): pybitshares wallet password
    """

    def mark_as_paid(client, nonce, number):
        """
        update the stakes database for this payment from "processing" to "paid"

        :param str(client): bitshares username of staking client
        :param int(nonce): munix timestamp *originally* associated with this stake
        :param int(number): the counting number of this interest payment
        :return None:
        """

        cur = con.cursor()
        query = (
            "UPDATE stakes WHERE "
            + "user=? AND nonce=? AND number=? "
            + "AND status=processing AND (type=interest OR type=principal)"
            + "SET (status=paid, block=?, processed=?)"
        )
        values = (
            client,
            nonce,
            number,
            get_block_num_current(),
            munix(),
        )
        cur.execute(query, values)
        # commit the database edit
        con.commit()

    def make_payout_process(amount, client, nonce, number, keys):
        """
        attempt to make simple payout

        if success:
            mark stake interest payment as "paid" in database
            add receipt to database

        if failed:
            attempt to move funds from bittrex and try again

            if failed:
                send 1 bts to client from bmg w/ support memo
                mark stake interest payment as "delinquent" in database

            if success:
                mark stake interest payment as "paid" in database
                add receipt to db for tx to client
                add receipt to db for tx from bittrex to bmg

        :param int(amount): the amount due to client
        :param str(client): bitshares username of staking client
        :param int(nonce): munix timestamp *originally* associated with this stake
        :param int(number): the counting number of this interest payment
        :param dict(keys): pybitshares wallet password
        :return None:
        """

        memo = f"Payment for stakeBTS {nonce} - {number}, we appreciate your business!"
        # check how much funds we have on hand in the brokerage account
        need = amount + 10
        pybitshares_balance = get_balance_pybitsares()
        # assuming we have enough, just pay the client his due
        if pybitshares_balance > need:
            msg = post_withdrawal_pybitshares(amount, client, keys, memo)
            update_receipt_database(nonce, msg, con)
            mark_as_paid(client, nonce, number)
        # if we don't have enough we'll have to move some BTS from bittrex to broker
        else:
            failed = True
            try:
                # calculate our deficit and and fetch our bittrex account balances
                deficit = need - pybitshares_balance
                bittrex_balance = get_balance_bittrex(keys)
                # assuming we can cover it with bittrex balances
                if sum(bittrex_balance.values()) > deficit:
                    # we start moving funds until we have just enough in the brokerage acct
                    for api in range(1, 4):
                        bittrex_available = bittrex_balance[api]
                        if bittrex_available > 510:
                            qty = min(deficit, bittrex_available - 10, 500)
                            msg = post_withdrawal_bittrex(qty, BROKER, keys, api)
                            update_receipt_database(nonce, msg, con)
                            deficit -= qty
                            if deficit <= 0:
                                break
                # wait up to ten minutes for funds to arrive:
                if deficit <= 0:
                    failed = False
                    begin = time.time()
                    while get_balance_pybitsares() < need:
                        time.sleep(10)
                        if time.time() - begin > 600:
                            failed = True
                            break
            except Exception as error:
                update_receipt_database(nonce, str(number) + " " + error, con)

            # send the client an IOU with support details
            if failed:
                memo = (
                    f"your stakeBTS payment of {amount} failed for an unknown reason, "
                    + "please contact complaints@stakebts.bitsharesmanagement.group "
                    + f"stake {nonce} - {number}"
                )
                msg = post_withdrawal_pybitshares(amount, client, keys, memo)
                update_receipt_database(nonce, msg, con)
            # pay the client if we have funds
            else:
                msg = post_withdrawal_pybitshares(amount, client, keys, memo)
                update_receipt_database(nonce, msg, con)
                mark_as_paid(client, nonce, number)

    block = get_block_num_current()
    now = munix()
    cur = con.cursor()
    # gather list of payments due
    query = (
        "SELECT (amount, client, start, number) FROM stakes "
        + "WHERE nonce<? "
        + "AND (type=principal OR type=interest) AND status=pending"
    )
    values = (now,)
    cur.execute(query, values)
    payments_due = cur.fetchall()
    # update principal and interest due status to paid
    query = (
        "UPDATE stakes WHERE nonce<? "
        + "AND (type=principal OR type=interest) AND status=pending"
        + "SET (status=processing, block=?, processed=?)"
    )
    values = (
        now,
        block,
        now,
    )
    cur.execute(query, values)
    # update penalties due to status aborted
    query = (
        "UPDATE stakes WHERE nonce<? "
        + "AND type=penalty AND status=pending"
        + "SET (status=aborted, block=?, processed=?)"
    )
    values = (
        now,
        block,
        now,
    )
    cur.execute(query, values)
    # commit the database edit
    con.commit()
    # make payments
    processes = {}
    for payment in payments_due:
        time.sleep(0.2)  # reduce likelihood of race condition
        amount = payment[0]
        client = payment[1]
        nonce = payment[2]
        number = payment[3]
        # each outbound payment will be contained within a subprocess
        processes[payment] = Thread(
            target=make_payout_process,
            args=(
                deepcopy(amount),
                deepcopy(client),
                deepcopy(nonce),
                deepcopy(number),
                keys,
            ),
        )
        processes[payment].start()


def main():
    """
    login then begin while loop listening for client requests and making timely payouts
    """
    con = sql(DB)
    keys = login()
    while True:
        listener(keys, con)
        # we'll launch payouts in a thread
        Thread(target=make_payouts, args=(keys, con))
        time.sleep(15)  # attempt to batch things ever 5 blocks or so


if __name__ == "__main__":

    main()
