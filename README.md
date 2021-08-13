
## StakeBTS Python Bot

`VERSION`

# v2.0

`INTALLATION`

**Install SQLite3:**
```shell
apt install -y sqlite3
```

**Create investment.db from db_setup.txt file:**

```sqlite3 investment.db```

(Copy/paste content of db_setup.txt)

```.quit```

**Create and activate environment:**
```shell
python3 -m venv env
source env/bin/activate
```

**Install requirements into environment:**
```shell
pip3 install -r requirements.txt
```

**Run app**

```
python3.8 stake_bitshares.py
```

`
CHANGELIST v2.0
`

- previously payouts were occurring at end of month
- all future payouts will occur in 30 day intervals from beginning of contract
- if you were paid early previously this may mean up to 59 days until next payout
- all payout amounts will be rounded down to nearest whole bitshare
- user will receive receipt as memo w/ 1 BTS upon creating a new contract
- all payouts will come from bitsharesmanagement.group
- in the event of payout failure, 1 BTS will be sent with additional support info
- client sends an invalid amount or invalid memo he will be refuned less 50 BTS penalty
- manager can use bot to transfer funds to and from bittrex to brokerage account
- manager can use bot to personally loan funds to the brokerage account
- new database format, all payouts are added to database at start of contract
- new database format, all outbound payment details are kept as receipts
- in the event brokerage account is low on funds, bot will pull from bittrex accounts
- all current payouts due are grouped into a thread
- each individual payout is now a time limited subprocess
- apscheduler has been replaced by marking databased payments paid as they are paid


`NOTES`


**Account that manager will use for the bot must be imported with all 3 private keys:**
**(Owner, Active and Memo) into uptick.**

**On BOT start you will be asked to enter your uptick WALLET password**

**Bittrex api is used for outbound payments.**
**You must also have Bittrex API key/secret.**
**This will be repeated for all 3 Bittrex corporate accounts.**

**All timestamps are integers in milleseconds**
**All amounts of funds stored in DB and sent are integers of BTS**

**Nothing is ever removed from the database**

`FUNCTIONS`

- pybitshares_reconnect()

    create locked owner and memo instances of the pybitshares wallet

- send_receipt(client, memo, keys)

    send client one BTS with memo to confirm new stake from pybitshares wallet

- bittrex_withdrawal(amount, client, keys)

    send funds using the bittrex api

- update_receipt_database(nonce, msg)

    upon every audit worthy event update the receipt database with
    the event millesecond timestamp and a pertinent message

- new_stake(nonce, block, client, amount, months, keys)

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
    number      - interest payments are numbered 1,2,3, etc. all other payments are 0

- end_stake_prematurely(nonce, block, client, keys)

    send principal less penalty from bittrex
    update database with principal and penalty paid; outstanding interest aborted

- get_block_num_current()

    connect to node and get the irreversible block number

- check_block(block_num, block, keys)

    check for client transfers to the broker in this block

  - get_json_memo(keys, trx):

      using the memo key, decrypt the memo in the client's deposit

- login()

    user input login credentials for pybitshares and bittrex

  - authenticate(keys)

      make authenticated request to pybitshares wallet and bittrex to test login

- listener(keys)

    get the last block number checked from the database
    and the latest block number from the node
    check each block in between for stake related transfers from clients
    then update the last block checked in the database

  - get_block_num_database():

      what is the last block number checked in the database?

  - set_block_num_database(block_num):

      update the block number last checked in the database

- make_payouts(keys)

    make all interest and principal payments due
    mark interest and principal paid in database
    mark penalties due as aborted in database
    set processed time and block to current for all
    send payments via bittrex api

- main()

    login then begin while loop listening for client requests and making timely payouts


`WORKFLOW`

    login

    while True:

        check node for new stakes or requests to stop stakes to appear on chain

            if any new stakes
                send 1 BTS receipt via pybitshares
                add contract_{months} to database, mark paid 1
                move all potential payouts/penalties due to database, mark pending

            if any stops
                send premature payout via bittrex
                mark paid/aborted/premature in database as applicable

        make periodic payments to clients as they become due by unix stamp

            if any due
                send payment via bittrex
                mark payments due paid in database as applicable
                mark penalties due aborted


`JSON FORMAT`
{"type":"<LENGTH_OF_STAKE>"}

`LENGTH_OF_STAKE`
- "three_months"
- "six_months"
- "twelve_months"
- "stop"

`DATABASE`

CREATE TABLE block (
    block INTEGER           # bitshares block number last checked by bot
);

- NOTE all payments *potentially* due
- are entered into "stakes" TABLE at start of contract
- as events unfold, their "status", "block", and "processed" time changes

    CREATE TABLE stakes (
        user TEXT               # bitshares user name for client
        token TEXT              # bitshares asset name
        amount INTEGER          # amount of asset rounded to nearest integer
        type TEXT               # contract, principal, penalty, or interest
        start INTEGER           # munix start time of contract
        due INTEGER             # munix due date of this payment
        processed INTEGER       # munix time at which payment was actually processed
        status TEXT             # pending, paid, aborted, or premature
        block INTEGER           # bitshares block number associated with this payment
        number INTEGER          # counting number for interest payments, eg 1,2,3,4...
    );

    CREATE TABLE receipts (
        nonce INTEGER           # munix start time of contract
        now INTEGER             # munix moment when event occurred
        msg TEXT                # receipt details for audit trail
    );

INSERT INTO block (block) VALUES (59120000); # the initial starting block

`preexisting_contracts.py and import_data.py`

preexisting_contracts.py houses a single global constant of block text in format:

username milliseconds_unix amount contract_length months_paid

can be tab or space delimited, eg:

    STAKES = """
        user1233 1623177720000 25000 12 2
        user9043 1623176546500 50000  3 2
    """

import_data.py moves those existing contracts to the database in the same
manner as all other contracts thereafter.


`SPONSOR`

This software is sponsored and managed by BitShares Management Group Limited

`DEVELOPERS`

v1.0 initial prototype
- iamredbar

v2.0 refactor, refinement, added features
- litepresence: finitestate@tutamail.com
