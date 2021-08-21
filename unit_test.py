"""
BitShares.org StakeMachine
unit test "get balance" and "post withdrawal" to bittrex and local pybitshares wallet
BitShares Management Group Co. Ltd.
"""

from stake_bitshares.py import (
    post_withdrawal_bittrex,
    post_withdrawal_pybitshares,
    get_balance_bittrex,
    get_balance_pybitshares,
    login,
)
from config import BROKER

print("\033c")
print("for this unit test you can input same api keys for all bittex accounts")

input("\npress Enter to continue\n")
keys = login()

print("get_balance_bittrex",    get_balance_bittrex(keys))
print("get_balance_pybitshares",    get_balance_pybitshares())

amount = 1
client = BROKER
api = 1
memo = "hello world"

print(
    f"post_withdrawal_bittrex({amount}, {client}, keys, {api})",
    post_withdrawal_bittrex(amount, client, keys, api)
)

print(
    f"post_withdrawal_pybitshares({amount}, {client}, keys, {memo})"
    post_withdrawal_pybitshares(amount, client, keys, memo)
)

