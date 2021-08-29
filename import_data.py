"""
BitShares.org StakeMachine
Import Old Contracts to Database Upon Initialization
BitShares Management Group Co. Ltd.
"""

# STANDARD MODULES
import datetime
from sqlite3 import connect as sql

# STAKEBTS MODULES
from config import DB
from preexisting_contracts import STAKES
from rpc import pybitshares_reconnect
from stake_bitshares import stake_start

# USER DEFINED CONSTANTS
JUNE30 = 1625011200000
JULY31 = 1627689600000
BLOCK0 = 1445838432000  # assuming perfect blocktime, calculated Aug 7, 2021


def convert_date_to_munix(date, fstring="%m/%d/%Y %H:%M"):
    """
    convert from human readable to millesecond epoch
    not used by this app because our data is already in millesecond epoch
    :param str(date): human readable date
    :param str(fstring): format of readable date
    :return int(): millesecond unix epoch
    """
    date_time_obj = datetime.datetime.strptime(date, fstring)
    return int(date_time_obj.timestamp() * 1000)


def get_dynamic_globals():
    """
    not actually used by this script,
    but allows us to associate a recent block num to unix time for dev
    :return dict():
    """
    bitshares, _ = pybitshares_reconnect()
    print(bitshares.rpc.get_dynamic_global_properties())


def convert_stakes_to_matrix(stakes):
    """
    STAKES is a block of text, we'll need to import that to python list of lists
    data must be in space seperated column format:
    username, munix, amount, term_in_months, months_prepaid
    :param str(stakes): multi-line space delimited text field
    :return matrix [[],[],[],...]:
    """
    return [i.strip().split() for i in stakes.splitlines() if i]


def convert_munix_to_block(munix):
    """
    approximate a blocktime given a millesecond unix timestamp, eg:
    NOTE: bitshares block is 3 seconds
    blocktime           btime unix     irr block
    2021-08-07T11:45:39 = 1628336739 = 60832769
    60832769 * 3 = 182498307 seconds
    T0 = 1628336739 - 182498307 = 1445838432
    unix - T0 / 3 = block number
    :param int(munix): timestamp in milleseconds since epoch
    :return int(): block number
    """
    return int((int(munix) / 1000 - BLOCK0 / 1000) / 3)


def add_block_num(stake_matrix):
    """
    our stake matrix has unix timestamps, we'll add approximate block number
    :param matrix(stake_matrix): text database converted to python list of lists
    :return matrix [[],[],[],...]:
    """
    for item, stake in enumerate(stake_matrix):
        stake_matrix[item].append(convert_munix_to_block(stake[1]))
    return stake_matrix


def mark_prepaid_stakes(stake_matrix, con):
    """
    make database changes to mark payments prepaid as "paid" with appropriate munix
    :param matrix(stake_matrix): text database converted to python list of lists
    :param object(con): database connection
    :return None:
    """
    cur = con.cursor()
    # search through our prepaid stake matrix for payments already made
    for stake in stake_matrix:
        # extract the user name and number of payments already executed
        client = str(stake[0])
        prepaid = int(stake[4])
        # handle cases where one payment has been sent already
        if prepaid == 1:
            block = convert_munix_to_block(JULY31)
            query = (
                "UPDATE stakes "
                + "SET status='paid', block_processed=?, processed=? "
                + "WHERE client=? AND type='interest' AND status='pending' AND number='1'"
            )
            values = (block, JULY31, client)
            print(query)
            print(values)
            print([type(i) for i in values])
            cur.execute(query, values)
        # handle cases where two payments have been sent already
        if prepaid == 2:
            block = convert_munix_to_block(JUNE30)
            query = (
                "UPDATE stakes "
                + "SET status='paid', block_processed=?, processed=? "
                + "WHERE client=? AND type='interest' AND status='pending' AND number='1'"
            )
            values = (block, JUNE30, client)
            print(query)
            print(values)
            print([type(i) for i in values])
            cur.execute(query, values)
            block = convert_munix_to_block(JULY31)
            query = (
                "UPDATE stakes "
                + "SET status='paid', block_processed=?, processed=? "
                + "WHERE client=? AND type='interest' AND status='pending' AND number='2'"
            )
            print(query)
            print(values)
            print([type(i) for i in values])
            values = (block, JULY31, client)
            cur.execute(query, values)
    # commit edit to database
    con.commit()


def initialize_database_with_existing_contracts():
    """
    primary event loop to initialize the database with existing contracts
    :return None:
    """
    con = sql(DB)
    # convert text block to a matrix
    stake_matrix = convert_stakes_to_matrix(STAKES)
    # add block number to each row in matrix
    stake_matrix = add_block_num(stake_matrix)
    # add stakes to database
    for stake in stake_matrix:
        params = {
            "client": str(stake[0]),
            "nonce": int(stake[1]),
            "amount": int(stake[2]),
            "months": int(stake[3]),
            "block": int(convert_munix_to_block(int(stake[1]))),
        }
        stake_start(params, con)
    # mark payouts already made as paid
    mark_prepaid_stakes(stake_matrix, con)
    # display results and close db connection
    # query = ".schema stakes"
    # print(query)
    # con.execute(query)
    query = "PRAGMA table_info(stakes);"
    print(query)
    con.execute(query)
    query = "SELECT * from stakes;"
    print(query)
    con.execute(query)
    con.close()


if __name__ == "__main__":
    initialize_database_with_existing_contracts()
