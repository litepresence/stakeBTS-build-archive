"""
BitShares.org StakeMachine
User Input
BitShares Management Group Co. Ltd.
"""

# USER DEFINED CONSTANTS
DB = "stake_bitshares.db"
NODE = "wss://node.market.rudex.org"
EMAIL = "complaints@stakebts.bitsharesmanagement.group"
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
# REPLAY #
# True : start from block number last checked in database
# False : start from current block number
# int() : start from user specified block number
REPLAY = False
# UNIT TESTING MODE
DEV = True
