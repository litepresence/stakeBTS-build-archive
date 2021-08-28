"""
BitShares.org StakeMachine
Hung Payment Handler
BitShares Management Group Co. Ltd.
"""

# STANDARD PYTHON MODULES
from getpass import getpass

# STAKE BTS MODULES
from config import BROKER
from stake_bitshares import payment_parent
from utilities import munix, sql_db


def main():
    """
    Handle hung payments with status "processing" due to insufficient funds
    """
    print("\033c")
    # read from database gather list of payments due
    query = (
        "SELECT amount, client, start, number, type FROM stakes "
        + "WHERE (type='principal' OR type='interest') AND due<? "
        + "AND status='processing'"
    )
    values = (munix(),)
    payments_due = sql_db(query, values)
    print(payments_due)
    choice = input("\ny + Enter to make these payments, or just Enter to abort\n")

    if choice == "y":
        keys = {
            "broker": BROKER,
            "password": getpass(
                f"\nInput Pybitshares Password for {BROKER} and press ENTER:\n"
            ),
        }
        payment_parent(payments_due, keys)


if __name__ == "__main__":

    main()
