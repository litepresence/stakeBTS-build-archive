"""
BitShares.org StakeMachine
Import Old Contracts to Database Upon Initialization
BitShares Management Group Co. Ltd.
"""

# STANDARD IMPORTS
import datetime

# PYBITSHARES IMPORTS
from stake_bitshares import pybitshares_reconnect, new_stake

# STAKEBTS IMPORTS
from preexisting_contracts import STAKES

# USER DEFINED CONSTANTS
DB = "stake_bitshares.db"
# in milleseconds
JUNE30 = 1625011200000
JULY31 = 1627689600000
BLOCK0 = 1445838432000  # assuming perfect blocktime, calculated Aug 7, 2021


def convert_date_to_munix(date, fstring="%m/%d/%Y %H:%M"):
    """
    convert from human readable to millesecond epoch
    not used by this app because our data is already in millesecond epoch
    """
    date_time_obj = datetime.datetime.strptime(date, fstring)
    unix = date_time_obj.timestamp()
    munix = int(unix * 1000)
    return munix


def get_dynamic_globals():
    """
    not actually used by this script,
    but allows us to associate a recent block num to unix time for dev
    """
    bitshares, _ = pybitshares_reconnect()
    print(bitshares.rpc.get_dynamic_global_properties())


def convert_stakes_to_matrix(stakes):
    """
    STAKES is a block of text, we'll need to import that to python list of lists
    data must be in space seperated column format:
    username, munix, amount, term_in_months, months_prepaid
    """
    stake_matrix = [i.strip().split() for i in stakes.splitlines() if i]
    # for stake in stake_matrix:
    #    print(stake)
    return stake_matrix


def convert_munix_to_block(munix):
    """
    approximate a blocktime given a millesecond unix timestamp, eg:

    NOTE: bitshares block is 3 seconds

    blocktime           btime unix     irr block
    2021-08-07T11:45:39 = 1628336739 = 60832769
    60832769 * 3 = 182498307 seconds
    T0 = 1628336739 - 182498307 = 1445838432
    unix - T0 / 3 = block number
    """

    block = int((int(munix) / 1000 - BLOCK0 / 1000) / 3)

    return block


def add_block_num(stake_matrix):
    """
    our stake matrix has unix timestamps, we'll add approximate block number
    """
    for item, stake in enumerate(stake_matrix):
        stake_matrix[item].append(convert_munix_to_block(stake[1]))
    # for stake in stake_matrix:
    #     print(stake)
    return stake_matrix


def mark_prepaid_stakes(stake_matrix):
    """
    make database changes to mark payments prepaid as "paid" with appropriate munix
    """
    # open stake_bitshares.db
    con = sql(DB)
    cur = con.cursor()
    # search through our prepaid stake matrix for payments already made
    for stake in stake_matrix:
        # extract the user name and number of payments already executed
        user = stake[0]
        prepaid = stake[4]
        # handle cases where one payment has been sent already
        if prepaid == 1:
            block = convert_munix_to_block(JULY31)
            query = (
                f"UPDATE stakes WHERE user={user} "
                + f"AND (type=interest) AND status=pending AND number=1"
                + f"SET (status=paid, block={block}, processed={JULY31})"
            )
            cur.execute(query)
        # handle cases where two payments have been sent already
        if prepaid == 2:
            block = convert_munix_to_block(JUNE30)
            query = (
                f"UPDATE stakes WHERE user={user} "
                + f"AND (type=interest) AND status=pending AND number=1"
                + f"SET (status=paid, block={block}, processed={JUNE30})"
            )
            cur.execute(query)
            block = convert_munix_to_block(JULY31)
            query = (
                f"UPDATE stakes WHERE user={user} "
                + f"AND (type=interest) AND status=pending AND number=2"
                + f"SET (status=paid, block={block}, processed={JULY31})"
            )
            cur.execute(query)
    # commit and close the database
    con.commit()
    con.close()


def initialize_database_with_existing_contracts():
    """
    primary event loop to initialize the database with existing contracts
    """
    # convert text block to a matrix
    stake_matrix = convert_stakes_to_matrix(STAKES)
    # add block number to each row in matrix
    stake_matrix = add_block_num(stake_matrix)
    # add stakes to database
    for stake in matrix:
        client = stake[0]
        nonce = stake[1]
        amount = stake[2]
        months = stake[3]
        new_stake(nonce, block, client, amount, months)
    # mark payouts already made as paid
    mark_prepaid_stakes(stake_matrix)


if __name__ == "__main__":

    initialize_database_with_existing_contracts()
