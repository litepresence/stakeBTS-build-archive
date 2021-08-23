"""
BitShares.org StakeMachine
Interest Payments on Staking
BitShares Management Group Co. Ltd.
"""
# DISABLE SELECT PYLINT TESTS
# pylint: disable=broad-except, bad-continuation, invalid-name

# STANDARD IMPORTS
import inspect
import time
from copy import deepcopy
from getpass import getpass
from json import dumps as json_dumps
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
from config import (
    BITTREX_1,
    BITTREX_2,
    BITTREX_3,
    BITTREX_ACCT,
    BROKER,
    DB,
    DEV,
    EMAIL,
    INTEREST,
    INVEST_AMOUNTS,
    MANAGERS,
    NODE,
    PENALTY,
    REPLAY,
)

# GLOBAL CONSTANTS
MUNIX_MONTH = 86400 * 30 * 1000
CLIENT_MEMOS = {
    "stop"  # client stops all outstanding contracts
    "three_months"  # client creates 3 month contract
    "six_months"  # client creates 6 month contract
    "twelve_months"  # client creates 12 month contract
}
ADMIN_MEMOS = {
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


def line_info():
    """
    :return tuple(current filename, function, and line number:
    """
    info = inspect.getframeinfo(inspect.stack()[1][0])
    return str((info.filename, info.function, info.lineno))


# CONNECT WALLET TO BITSHARES NODE
def pybitshares_reconnect():
    """
    create locked owner and memo instances of the pybitshares wallet
    """
    bitshares = BitShares(node=NODE, nobroadcast=False)
    set_shared_bitshares_instance(bitshares)
    memo = Memo(blockchain_instance=bitshares)
    return bitshares, memo


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
            msg += str(bittrex_api.post_withdrawal(**params))
        except Exception as error:
            msg = f"bittrex failed to send {amount} to client {client}, due to {error}"
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
    msg = f"POST WITHDRAWAL PYBITSHARES {amount} {client} {memo}"
    print(it("yellow", msg))
    if not DEV:
        try:
            bitshares, _ = pybitshares_reconnect()
            bitshares.wallet.unlock(keys["password"])
            msg += str(
                bitshares.transfer(client, amount, "BTS", memo, account=keys["broker"])
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
                balance = int(
                    [
                        i
                        for i in bittrex_api.get_balances()
                        if i["currencySymbol"] == "BTS"
                    ][0]["available"]
                )
            except Exception:
                pass
            balances[api] = balance
            print("bittrex balances:", balances)
    return balances


def get_balance_pybitshares():
    """
    get the broker's BTS balance
    :return int(): BTS balance
    """
    _, _ = pybitshares_reconnect()
    account = Account(BROKER)
    balance = int(account.balance("BTS")["amount"])
    if DEV:
        balance = NINES
    print("pybitshares balance:", balance)
    return balance


# SQL DATABASE GET AND SET BLOCK NUMBER
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


# SQL DATABASE RECEIPTS
def update_receipt_database(nonce, msg, con):
    """
    upon every audit worthy event update the receipt database with
    the event millesecond timestamp and a pertinent message
    :param int(nonce): *start* munix timestamp associated with this stake
    :param str(msg): auditable event documentation
    :return None:
    """
    cur = con.cursor()
    query = "INSERT INTO receipts (nonce, now, msg) VALUES (?,?,?)"
    values = (nonce, munix(), msg)
    print(query, values)
    cur.execute(query, values)
    # commit the database edit
    con.commit()


# SQL DATABASE START, STOP, MARK PAID
def stake_start(params, con, keys=None):
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
    :params int(nonce): munix timestamp *originally* associated with this stake
    :params int(block): block number when this stake began
    :params str(client): bitshares username of staking client
    :params int(amount): the amount the client is staking
    :params int(months): the number of months the client is staking
    :param object(con): sql db connection
    :param dict(keys): pybitshares wallet password
    :return None:
    """
    # localize parameters
    nonce, block, client, amount, months = map(
        params.get, ("nonce", "block", "client", "amount", "months")
    )
    # keys are None when using import_data.py to add existing contracts
    if keys is not None:
        # send confirmation receipt to client with memo using pybitshares
        memo = f"{months} stake contract for {amount} BTS received timestamp {nonce}"
        memo += post_withdrawal_pybitshares(1, client, memo, keys)
        memo += json_dumps(params)
        update_receipt_database(nonce, memo, con)
    # open the database
    cur = con.cursor()
    # insert the contract into the stakes database
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
        f"contract_{months}",
        nonce,  # start now
        nonce,  # due now
        nonce,  # processed now
        "paid",
        block,
        NINES,
        0,
    )
    cur.execute(query, values)
    # insert the principal into the stakes database
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
        nonce + months * MUNIX_MONTH,  # due at end of term
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
    query = (
        "INSERT INTO stakes "
        + "(client, token, amount, type, start, due, processed, status, "
        + "block_start, block_processed, number) "
        + "VALUES (?,?,?,?,?,?,?,?,?,?,?)"
    )
    values = (
        client,
        "BTS",
        int(-1 * amount * PENALTY),  # entered as negative value
        "penalty",
        nonce,
        nonce + months * MUNIX_MONTH,  # due at end of term
        0,
        "pending",
        block,
        NINES,
        0,
    )
    cur.execute(query, values)
    # insert the interest payments into the stakes database
    for month in range(1, months + 1):
        query = (
            "INSERT INTO stakes "
            + "(client, token, amount, type, start, due, processed, status, "
            + "block_start, block_processed, number) "
            + "VALUES (?,?,?,?,?,?,?,?,?,?,?)"
        )
        values = (
            client,
            "BTS",
            int(amount * INTEREST),
            "interest",
            nonce,
            nonce + month * MUNIX_MONTH,  # due monthly
            0,
            "pending",
            block,
            NINES,
            month,
        )
        cur.execute(query, values)
    # commit the database edit
    con.commit()


def stake_stop(params, con, keys):
    """
    send principal less penalty from pybitshares wallet
    update database with principal and penalty paid; outstanding interest aborted
    :param int(nonce): munix timestamp *originally* associated with this stake
    :param int(block): block number when this stake began
    :param str(client): bitshares username of staking client
    :param dict(keys): pybitshares wallet password
    :return None:
    """
    # localize parameters
    nonce, block, client = map(params.get, ("nonce", "block", "client"))
    # open db connection and query principal and and penalties due to client
    cur = con.cursor()
    query = (
        "SELECT amount FROM stakes "
        + "WHERE client=? AND (type='principal' OR type='penalty')"
    )
    values = (client,)
    cur.execute(query, values)
    # principal less penalty
    amount = int(sum(cur.fetchall()))
    # send premature payment to client
    params["amount"] = amount
    params["number"] = 0
    params["type"] = "stop"
    thread = Thread(target=payment_child, args=(deepcopy(params), keys,),)
    thread.start()
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


def stake_paid(params, con):
    """
    update the stakes database for this payment from "processing" to "paid"
    :param str(client): bitshares username of staking client
    :param int(nonce): munix timestamp *originally* associated with this stake
    :param int(number): the counting number of this interest payment
    :return None:
    """
    client, nonce, number = map(params.get, ("client", "nonce", "number"))
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


# SERVE MEMO REQUESTS
def serve_client(params, con, keys):
    """
    create new stake or stop all stakes
    :params dict(memo):
    :params int(amount):
    :params str(client):
    :params int(block_num):
    :param object(con):
    :param dict(keys):
    :return str(msg):
    """
    # localize parameters
    memo, amount, client, block_num = map(
        params.get, ("memo", "amount", "client", "block_num"),
    )
    # new client wants to stake and used a valid memo
    if memo["type"] in [
        "three_months",
        "six_months",
        "twelve_months",
    ]:
        months = MONTHS[memo["type"]]
        # client sent a valid amount and memo to start a new stake
        msg = (
            f"received new stake from {client} in {block_num} "
            + f"for {months} months and {amount} amount"
        )
        stake_start(params, con, keys)
    # existing client wishes to stop all his stake contracts prematurely
    elif memo["type"] == "stop":
        msg = f"received stop demand from {client} in {block_num}"
        stake_stop(params, con, keys)
    return msg


def serve_admin(params, keys):
    """
    transfer funds to and from bittrex or loan funds to brokerage account
    :params dict(memo):
    :params int(amount):
    :params str(client):
    :param dict(keys):
    :return str(msg):
    """
    # localize parameters
    memo, amount, client = map(params.get, ("memo", "amount", "client"))
    msg = f"admin request failed {(client, amount, memo)}"
    # the manager wishes to move funds from bittrex to broker
    if memo["type"] == "bittrex_to_bmg":
        try:
            amount = int(memo["amount"])
            api = int(memo["api"])
            assert api in [1, 2, 3]
            assert amount > 1000
            msg = post_withdrawal_bittrex(amount, client, api, keys)
        except Exception:
            pass
    # the manager wishes to move funds from broker to bittrex
    elif memo["type"] == "bmg_to_bittrex":
        try:
            amount = int(memo["amount"])
            api = int(memo["api"])
            assert api in [1, 2, 3]
            assert amount > 1000
            decode_api = {1: BITTREX_1, 2: BITTREX_2, 3: BITTREX_3}
            bittrex_memo = decode_api[api]
            msg = (
                memo["type"]
                + bittrex_memo
                + post_withdrawal_pybitshares(
                    int(amount), BITTREX_ACCT, keys, bittrex_memo
                )
            )
        except Exception:
            pass
    # the manager has loaned the broker personal funds
    elif memo["type"] == "loan_to_bmg":
        amount = int(memo["amount"])
        msg = f"{client} has loaned the broker {amount}"
    return msg


def serve_invalid(params, keys):
    """
    client or admin has made an invalid request, return funds less fee
    :params dict(memo):
    :params int(amount):
    :params str(client):
    :params int(block_num):
    :params int(nonce):
    :param dict(keys):
    """
    # localize parameters
    memo, amount, client, nonce, block_num = map(
        params.get, ("memo", "amount", "client", "nonce", "block_num")
    )
    request_type = {
        "client_memo": memo in CLIENT_MEMOS,  # bool()
        "admin_memo": memo in ADMIN_MEMOS,  # bool()
        "admin": client in MANAGERS,  # bool()
        "invest_amount": amount in INVEST_AMOUNTS,  # bool()
        "ltm": Account(client).is_ltm,  # bool()
        "memo": memo,  # client's memo
        "amount": amount,  # amount sent by client
        "client": client,  # bitshares user name
        "nonce": nonce,  # start time of this ticket
        "block": block_num,  # block number client sent funds
    }
    msg = str("invalid request, 50 BTS fee charged", json_dumps(request_type))
    amount -= 50
    if amount > 10:
        msg += post_withdrawal_pybitshares(int(amount), client, msg, keys)
    return msg


# CHECK BLOCKS
def get_block_num_current():
    """
    connect to node and get the irreversible block number
    """
    bitshares, _ = pybitshares_reconnect()
    return bitshares.rpc.get_dynamic_global_properties()["last_irreversible_block_num"]


def check_block(block_num, block, con, keys):
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
        except Exception:
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
                amount = int(
                    trx[1]["amount"]["amount"] / 10 ** Asset("1.3.0").precision
                )
                params = {
                    "client": client,
                    "amount": amount,
                    "memo": memo,
                    "block_num": block_num,
                    "block": block,
                    "nonce": nonce,
                }
                if DEV:
                    print(it("green", "post withdrawal"), amount, client, memo)
                # handle requests to start and stop stakes
                if memo in CLIENT_MEMOS and amount in INVEST_AMOUNTS:
                    msg = serve_client(params, con, keys)
                # handle admin requests to move funds
                elif (
                    client in MANAGERS
                    and memo in ADMIN_MEMOS
                    and Account(client).is_ltm
                ):
                    msg = serve_admin(params, keys)
                # handle invalid requests
                else:
                    msg = serve_invalid(params, keys)
                update_receipt_database(nonce, msg, con)


# PAYMENTS
def payment_parent(payments_due, keys):
    """
    spawn payment threads
    :param matrix(payments_due): list of payments due;
        each with amount, client, nonce, number
    :return None:
    """
    threads = {}
    for payment in payments_due:
        time.sleep(0.1)  # reduce likelihood of race condition
        params = {
            "amount": payment[0],
            "client": payment[1],
            "nonce": payment[2],
            "number": payment[3],
            "type": payment[4],
        }
        # each individual outbound payment_child()
        # is a child of listener_sql(),
        # we'll use deepcopy so that the thread's locals are static to the payment
        threads[payment] = Thread(target=payment_child, args=(deepcopy(params), keys,),)
        threads[payment].start()


def payment_child(params, keys):
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
    :params int(amount): the amount due to client
    :params str(client): bitshares username of staking client
    :params int(nonce): munix timestamp *originally* associated with this stake
    :params int(number): the counting number of this interest payment
    :param dict(keys): pybitshares wallet password
    :return None:
    """
    amount, client, nonce, number = map(
        params.get, ("amount", "client", "nonce", "number")
    )
    con = sql(DB)
    print(it("green", str(("make payout process", amount, client, nonce, number))))
    memo = (
        f"Payment for stakeBTS nonce {nonce} type {params['type']} {number}, "
        + "we appreciate your business!"
    )
    # calculate need vs check how much funds we have on hand in the brokerage account
    params.update(
        {"need": amount + 10, "pybitshares_balance": get_balance_pybitshares()}
    )
    # if we don't have enough we'll have to move some BTS from bittrex to broker
    covered = True
    if params["pybitshares_balance"] < params["need"]:
        covered = payment_cover(params, con, keys)
    # assuming we have enough, just pay the client his due
    if covered:
        msg = post_withdrawal_pybitshares(amount, client, memo, keys)
        msg += json_dumps(params)
        update_receipt_database(nonce, msg, con)
        stake_paid(params, con)
    # something went wrong, send the client an IOU with support details
    else:
        memo = (
            f"your stakeBTS payment of {amount} failed for an unknown reason, "
            + f"please contact {EMAIL} "
            + f"BTSstake nonce {nonce} type {params['type']} {number}"
        )
        msg = memo + post_withdrawal_pybitshares(1, client, memo, keys)
        msg += json_dumps(params)
        update_receipt_database(nonce, msg, con)


def payment_cover(params, con, keys):
    """
    when there are not enough funds in pybitshares wallet
    move some funds from bittrex, check all 3 corporate api accounts
    :param int(need): the amount due to client + 10
    :param str(client): the amount in broker account
    :param dict(keys): pybitshares wallet password and bittrex keys
    :param int(nonce): munix timestamp *originally* associated with this stake
    :param int(number): the counting number of this interest payment
    :param object(con): a database connection
    :return bool(): whether of not we have enough funds to cover this payment
    """
    need, pybitshares_balance, nonce = map(
        params.get, ("need", "pybitshares_balance", "nonce")
    )
    covered = False
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
                    msg = "cover payment"
                    msg += post_withdrawal_bittrex(qty, BROKER, keys, api)
                    msg += json_dumps(params)
                    update_receipt_database(nonce, msg, con)
                    deficit -= qty
                    if deficit <= 0:
                        break  # eg. if 1st api has funds stop here
        # wait up to ten minutes for funds to arrive:
        if deficit <= 0:
            # breaks on timeout or on receipt of funds
            covered = True
            begin = time.time()
            while get_balance_pybitshares() < need:
                time.sleep(10)
                if time.time() - begin > 600:
                    covered = False
                    break
    except Exception as error:
        error = "cover payment failed" + json_dumps(params) + error
        update_receipt_database(nonce, error, con)
    return covered


# LISTENER THREADS
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
            check_block(block_num, block, con, keys)
            set_block_num_database(block_num, con)
        time.sleep(30)


def listener_sql(keys):
    """
    make all interest and principal payments due and marke them paid in database
    mark penalties due as aborted in database
    set processed time and block to current for all
    send individual payments using threading
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
            "SELECT amount, client, start, number, type FROM stakes "
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
        payment_parent(payments_due, keys)
        time.sleep(30)


# PRIMARY EVENT BACKBONE
def welcome(keys):
    """
    UX at startup
    """
    con = sql(DB)
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


def login():
    """
    user input login credentials for pybitshares and bittrex
    :return dict(keys): authenticated bittrex api keys and pybitshares wallet password
    """
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


def main():
    """
    login then begin while loop listening for client requests and making timely payouts
    """
    keys = login()
    welcome(keys)
    # branch into two run forever threads
    # block operations listener_bitshares for incoming client requests
    # this thread will contain a continuous while loop
    thread_1 = Thread(target=listener_bitshares, args=(keys))
    thread_1.start()
    # sql db payout listener_sql for payments now due
    # this thread will contain a continuous while loop
    # listener_sql() will launch child payment threads via payment_parent()
    thread_2 = Thread(target=listener_sql, args=(keys))
    thread_2.start()


if __name__ == "__main__":
    main()
