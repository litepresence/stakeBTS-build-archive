"""
BitShares.org StakeMachine
Interest Payments on Staking
BitShares Management Group Co. Ltd.
"""
# DISABLE SELECT PYLINT TESTS
# pylint: disable=broad-except, bare-except, bad-continuation, too-many-branches
# pylint: disable=too-many-statements, too-many-nested-blocks, too-many-arguments
# pylint: disable=too-many-locals, wildcard-import, invalid-name

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

# STAKE BTS IMPORTS
from bittrex_api import Bittrex
from config import *

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
NINES = 999999999

# UTILITIES
def it(style, text, foreground=True):
    """
    Color printing in terminal
    """
    lie = 4
    if foreground:
        lie = 3
    if isinstance(style, tuple):  # RGB
        return f"\033[{lie}8;2;{style[0]};{style[1]};{style[2]}m{str(text)}\033[0;00m"
    if isinstance(style, int):  # xterm-256
        return f"\033[{lie}8;5;{style}m{str(text)}\033[0;00m"
    # 6 color emphasis dict
    emphasis = {
        "red": 91,
        "green": 92,
        "yellow": 93,
        "blue": 94,
        "purple": 95,
        "cyan": 96,
    }
    return f"\033[{emphasis[style]}m{str(text)}\033[0m"


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
    msg = f"POST WITHDRAWAL BITTREX {amount} {client} {api}"
    print(it("yellow", msg))
    if not DEV:
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
    msg = f"POST WITHDRAWAL PYBITSHARES {amount} {client} {memo}"
    print(it("yellow", msg))
    if not DEV:
        try:
            bitshares, _ = pybitshares_reconnect()
            bitshares.wallet.unlock(keys["password"])
            msg += bitshares.transfer(
                client, amount, "BTS", memo, account=keys["broker"]
            )
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
    balances = {1: NINES, 2: NINES, 3: NINES}
    if not DEV:
        for api in range(1, 4):
            balance = 0
            try:
                bittrex_api = Bittrex(
                    api_key=keys[f"api_{api}_key"], api_secret=keys[f"api_{api}_secret"]
                )
                balance = [
                    i
                    for i in bittrex_api.get_balances()
                    if i["currencySymbol"] == "BTS"
                ][0]["available"]
            except:
                pass
            balances[api] = balance
            print("bittrex balances:", balances)
    return balances


def get_balance_pybitshares():
    """
    get the broker's BTS balance
    :return float(): BTS balance
    """
    _, _ = pybitshares_reconnect()
    account = Account(BROKER)
    balance = account.balance("BTS")["amount"]
    if DEV:
        balance = NINES
    print("pybitshares balance:", balance)
    return balance


# GET AND SET DATABASE BLOCK NUMBER
def set_block_num_database(block_num, con):
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


def get_block_num_database(con):
    """
    what is the last block number checked in the database?
    """
    cur = con.cursor()
    query = "SELECT block FROM block"
    cur.execute(query)
    block_num = int(cur.fetchall()[0][0])
    return block_num


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
    values = (nonce, munix(), msg)
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
        + "(client, token, amount, type, start, due, processed, status, "
        + "block_start, block_processed, number) "
        + "VALUES (?,?,?,?,?,?,?,?,?,?,?)"
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
        NINES,
        0,
    )
    cur.execute(query, values)
    # insert the principal into the stakes database
    due = nonce + months * MUNIX_MONTH
    query = (
        "INSERT INTO stakes "
        + "(client, token, amount, type, start, due, processed, status, "
        + "block_start, block_processed, number) "
        + "VALUES (?,?,?,?,?,?,?,?,?,?,?)"
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
        NINES,
        0,
    )
    print(query)
    print(values)
    print([type(i) for i in values])
    cur.execute(query, values)
    # insert the early exit penalty into the stakes database
    penalty = -1 * amount * PENALTY
    query = (
        "INSERT INTO stakes "
        + "(client, token, amount, type, start, due, processed, status, "
        + "block_start, block_processed, number) "
        + "VALUES (?,?,?,?,?,?,?,?,?,?,?)"
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
        NINES,
        0,
    )
    cur.execute(query, values)
    # insert the interest payments into the stakes database
    interest = amount * INTEREST
    for month in range(1, months + 1):
        due = nonce + month * MUNIX_MONTH
        query = (
            "INSERT INTO stakes "
            + "(client, token, amount, type, start, due, processed, status, "
            + "block_start, block_processed, number) "
            + "VALUES (?,?,?,?,?,?,?,?,?,?,?)"
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
            NINES,
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
        "SELECT amount FROM stakes "
        + "WHERE client=? AND (type='principal' OR type='penalty')"
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
        "UPDATE stakes "
        + "SET status='premature', processed=?, block_processed=? "
        + "WHERE client=? AND status='pending' AND type='principal'"
    )
    values = (nonce, block, client)
    cur.execute(query, values)
    query = (
        "UPDATE stakes "
        + "SET status='paid', processed=?, block_processed=? "
        + "WHERE client=? AND status='pending' AND type='penalty'"
    )
    values = (nonce, block, client)
    cur.execute(query, values)
    query = (
        "UPDATE stakes "
        + "SET status='aborted', processed=?, block_processed=? "
        + "WHERE client=? AND status='pending' AND type='interest'"
    )
    values = (nonce, block, client)
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
        for trx in trxs["operations"]:
            # if it is a BTS transfer to the broker managed account
            if (
                trx[0] == 0  # withdrawal
                and Account(trx[1]["to"]).name == keys["broker"]  # transfer to me
                and str(trx[1]["amount"]["asset_id"]) == "1.3.0"  # of BTS core token
            ):
                # provide timestamp, extract amount and client, dedode the memo
                msg = ""
                memo = get_json_memo(keys, trx)
                nonce = munix()
                client = Account(trx[1]["from"]).name
                amount = int(trx[1]["amount"]["amount"]) / (
                    10 ** Asset("1.3.0").precision
                )
                if DEV:
                    print(amount, client, memo)
                    post_withdrawal_pybitshares(int(amount), client, keys, "")
                elif client not in MANAGERS:
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
                            stake_start(
                                int(nonce),
                                int(block),
                                str(client),
                                int(amount),
                                int(months),
                                dict(keys),
                            )
                    # existing client wishes to stop all his stake contracts prematurely
                    elif memo["type"] == "stop":
                        msg = f"received stop demand from {client} in {block_num}"
                        stake_stop(nonce, block, client, keys, con)
                if client in MANAGERS:
                    valid = True
                    if Account(client).is_ltm:
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
                    # non ltm admin attempts to move funds
                    elif memo["type"] in ["bittrex_to_bmg", "bmg_to_bittrex"]:
                        msg = "DENIED: only ltm admin can transfer funds, "
                        msg += f"please contact {EMAIL} "
                        msg += post_withdrawal_pybitshares(0.1, client, keys, msg)
                    # non ltm attempts to loan to bmg
                    elif memo["type"] == "loan_to_bmg":
                        msg = "DENIED, only ltm can make loans to bmg, "
                        msg += f"refunding less 50 BTS penalty, please contact {EMAIL} "
                        amount -= 50
                        if amount > 10:
                            msg += post_withdrawal_pybitshares(
                                int(amount), client, keys, msg
                            )
                update_receipt_database(nonce, msg, con)


# PAYOUTS
def spawn_payments(payments_due, keys):
    """
    spawn payment threads
    :param matrix(payments_due): list of payments due;
        each with amount, client, nonce, number
    :return None:
    """
    threads = {}
    for payment in payments_due:
        time.sleep(0.1)  # reduce likelihood of race condition
        amount = payment[0]
        client = payment[1]
        nonce = payment[2]
        number = payment[3]
        # each individual outbound make_payout_thread()
        # is a child of listener_sql(),
        # we'll use deepcopy so that the thread's locals are static to the payment
        threads[payment] = Thread(
            target=make_payout_thread,
            args=(
                deepcopy(amount),
                deepcopy(client),
                deepcopy(nonce),
                deepcopy(number),
                keys,
            ),
        )
        threads[payment].start()


def make_payout_thread(amount, client, nonce, number, keys):
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
    con = sql(DB)
    print(it("green", str(("make payout process", amount, client, nonce, number))))
    memo = f"Payment for stakeBTS {nonce} - {number}, we appreciate your business!"
    # check how much funds we have on hand in the brokerage account
    need = amount + 10
    pybitshares_balance = get_balance_pybitshares()
    # assuming we have enough, just pay the client his due
    if pybitshares_balance > need:
        msg = post_withdrawal_pybitshares(amount, client, keys, memo)
        update_receipt_database(nonce, msg, con)
        mark_as_paid(client, nonce, number, con)
    # if we don't have enough we'll have to move some BTS from bittrex to broker
    else:
        failed = True
        try:
            # calculate our deficit and and fetch our bittrex account balances
            deficit = need - pybitshares_balance
            bittrex_balance = get_balance_bittrex(keys)  # returns dict()
            # assuming we can cover it with bittrex balances
            if sum(bittrex_balance.values()) > deficit:
                # we start moving funds until we have just enough in the brokerage acct
                for api in range(1, 4):
                    bittrex_available = bittrex_balance[api]
                    if bittrex_available > 510:
                        qty = min(deficit, bittrex_available - 10)
                        msg = post_withdrawal_bittrex(qty, BROKER, keys, api)
                        update_receipt_database(nonce, msg, con)
                        deficit -= qty
                        if deficit <= 0:
                            break
            # wait up to ten minutes for funds to arrive:
            if deficit <= 0:
                failed = False
                begin = time.time()
                while get_balance_pybitshares() < need:
                    time.sleep(10)
                    if time.time() - begin > 600:
                        failed = True
                        break
        except Exception as error:
            update_receipt_database(nonce, f"{number} {error}", con)
        # send the client an IOU with support details
        if failed:
            memo = (
                f"your stakeBTS payment of {amount} failed for an unknown reason, "
                + f"please contact {EMAIL} "
                + f"stake {nonce} - {number}"
            )
            msg = post_withdrawal_pybitshares(1, client, keys, memo)
            update_receipt_database(nonce, msg, con)
        # pay the client if we have funds
        else:
            msg = post_withdrawal_pybitshares(amount, client, keys, memo)
            update_receipt_database(nonce, msg, con)
            mark_as_paid(client, nonce, number, con)


def mark_as_paid(client, nonce, number, con):
    """
    update the stakes database for this payment from "processing" to "paid"
    :param str(client): bitshares username of staking client
    :param int(nonce): munix timestamp *originally* associated with this stake
    :param int(number): the counting number of this interest payment
    :return None:
    """
    cur = con.cursor()
    query = (
        "UPDATE stakes "
        + "SET status='paid', block_processed=?, processed=? "
        + "WHERE client=? AND start=? AND number=? AND status='processing' AND "
        + "(type='interest' OR type='principal')"
    )
    # note this is current block number not tx containing block
    values = (get_block_num_current(), munix(), client, nonce, number)
    if DEV:
        print(query, "\n", values)
    cur.execute(query, values)
    # commit the database edit
    con.commit()


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
    if DEV:
        keys = {
            "broker": BROKER,
            "password": "",
            "api_1_key": "",
            "api_1_secret": "",
            "api_2_key": "",
            "api_2_secret": "",
            "api_3_key": "",
            "api_3_secret": "",
        }
        return keys
    while not authenticated:
        keys = {
            "broker": BROKER,
            "password": getpass(
                f"\nInput Pybitshares Password for {BROKER} and " + "press ENTER:\n"
            ),
            "api_1_key": getpass("\nInput Bittrex API 1 Key and press ENTER:\n"),
            "api_1_secret": getpass("\nInput Bittrex API 1 Secret and press ENTER:\n"),
            "api_2_key": getpass("\nInput Bittrex API 2 Key and press ENTER:\n"),
            "api_2_secret": getpass("\nInput Bittrex API 2 Secret and press ENTER:\n"),
            "api_3_key": getpass("\nInput Bittrex API 3 Key and press ENTER:\n"),
            "api_3_secret": getpass("\nInput Bittrex API 3 Secret and press ENTER:\n"),
        }
        authenticated = authenticate(keys)
    return keys


def listener_bitshares(keys):
    """
    get the last block number checked from the database
    and the latest block number from the node
    check each block in between for stake related transfers from clients
    then update the last block checked in the database
    :param dict(keys): bittrex api keys and pybitshares wallet password
    """
    con = sql(DB)
    while True:
        block_last = get_block_num_database(con)
        block_new = get_block_num_current()
        for block_num in range(block_last + 1, block_new + 1):
            if block_num % 20 == 0:
                print(
                    it("blue", str((block_num, time.ctime(), int(1000 * time.time()))))
                )
            block = Block(block_num)
            Block.clear_cache()
            check_block(block_num, block, keys, con)
            set_block_num_database(block_num, con)
        time.sleep(30)


def listener_sql(keys):
    """
    make all interest and principal payments due
    mark interest and principal paid in database
    mark penalties due as aborted in database
    set processed time and block to current for all
    send payments via pybitshares wallet
    :param dict(keys): pybitshares wallet password
    """
    con = sql(DB)
    while True:
        # get millesecond timestamp and current block number
        now = munix()
        block = get_block_num_current()
        # open the database
        cur = con.cursor()
        # read from database
        # gather list of payments due
        query = (
            "SELECT amount, client, start, number FROM stakes "
            + "WHERE (type='principal' OR type='interest') AND due<? AND status='pending'"
        )
        values = (now,)
        # print(query, values)
        cur.execute(query, values)
        payments_due = cur.fetchall()
        # gather list of contracts that have matured
        query = (
            "SELECT amount, client, start, number FROM stakes "
            + "WHERE type='penalty' AND due<? AND status='pending'"
        )
        values = (now,)
        # print(query, values)
        cur.execute(query, values)
        closed_contracts = cur.fetchall()
        print(
            it("green", "payments due"),
            payments_due,
            it("red", "closed contracts"),
            closed_contracts,
        )
        # write to database
        # update principal and interest due status to processing
        query = (
            "UPDATE stakes "
            + "SET status='processing', block_processed=?, processed=? "
            + "WHERE (type='principal' OR type='interest') AND due<? AND status='pending'"
        )
        values = (block, now, now)
        cur.execute(query, values)
        # update penalties due to status aborted
        query = (
            "UPDATE stakes "
            + "SET status='aborted', block_processed=?, processed=? "
            + "WHERE type='penalty' AND due<? AND status='pending'"
        )
        values = (block, now, now)
        cur.execute(query, values)
        # commit the database edit then make the payments due
        con.commit()
        spawn_payments(payments_due, keys)
        time.sleep(30)


def welcome(keys, con):
    """
    UX at startup
    """
    block_num_current = get_block_num_current()
    print(it("blue", f"\033c\n{keys['broker'].upper()} AUTHENTICATED\n"))
    # display developer mode, replay type, and current block number locally vs actual
    if DEV:
        print(it("red", "\n     *** DEVELOPER MODE ***\n\n"))
    if isinstance(REPLAY, bool):
        if REPLAY:
            print("start - REPLAY - from last block in database")
        else:
            print("start - NO REPLAY - from current block number")
            set_block_num_database(block_num_current, con)
    elif isinstance(REPLAY, int):
        print(f"start - REPLAY - from user specified block number {REPLAY}")
        set_block_num_database(REPLAY - 1, con)
    print(
        "\n",
        "database block:",
        get_block_num_database(con),
        "current block:",
        block_num_current,
    )
    print(time.ctime(), int(1000 * time.time()), "\n")


def main():
    """
    login then begin while loop listening for client requests and making timely payouts
    """
    con = sql(DB)
    keys = login()
    welcome(keys, con)
    # block operations listener_bitshares for incoming client requests
    # this thread will contain a continuous while loop
    listener_thread = Thread(target=listener_bitshares, args=(keys))
    listener_thread.start()
    # sql db payout listener_bitshares for payments now due
    # this thread will contain a continuous while loop
    # listener_sql() will launch child payment threads via spawn_payments()
    payout_thread = Thread(target=listener_sql, args=(keys))
    payout_thread.start()


if __name__ == "__main__":
    main()
