"""
BitShares.org StakeMachine
unit test "get balance" and "post withdrawal" to bittrex and local pybitshares wallet
BitShares Management Group Co. Ltd.
"""

# STAKE BTS MODULES
from dev_auth import KEYS
from rpc import (get_balance_bittrex, get_balance_pybitshares,
                 post_withdrawal_bittrex, post_withdrawal_pybitshares)

# USER DEFINED CONSTANTS
AMOUNT = 1
CLIENT = "litepresence1"
API = 1
MEMO = "hello world"


def main():
    """
    test get balances and post withdrawals
    """
    print("get_balance_bittrex", get_balance_bittrex(KEYS))
    print("get_balance_pybitshares", get_balance_pybitshares())
    print(
        f"post_withdrawal_bittrex({AMOUNT}, {CLIENT}, {API}, keys)",
        post_withdrawal_bittrex(AMOUNT, CLIENT, API, KEYS),
    )
    print(
        f"post_withdrawal_pybitshares({AMOUNT}, {CLIENT}, {MEMO}, keys)",
        post_withdrawal_pybitshares(AMOUNT, CLIENT, MEMO, KEYS),
    )


if __name__ == "__main__":

    main()
