
## StakeBTS Python Bot

`APP VERSION`
**v2.0**

`PYTHON VERSION`
**3.8+**

`PYTHON REQUIREMENTS`
**bitshares**
**uptick**

`DESCRIPTION`
Recurring interest and principal payment automation
for bitsharesmanagement.group to stakeBTS clients

`INTALLATION`
**Install SQLite3:**
```
sudo apt install -y sqlite3
```

**Create stake_bitshares.db**
**set up the tables with db_setup.py file:**
**check the schema and that the stake table is empty**
```
sqlite3 stake_bitshares.db

.quit

python3.8 db_setup.py

sqlite3 stake_bitshares.db

.schema stakes
.schema block
.schema receipts

SELECT * FROM stakes;

.quit
```

**Create and activate environment:**
```
sudo apt-get install python3-venv
python3 -m venv env
source env/bin/activate
```

**Install requirements into environment:**
```
pip3 install -r requirements.txt
```

**import old client data**
```
python3.8 import_data.py
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
- each individual payout is also a thread
- apscheduler has been replaced by a custom database items due listener
- approved admin must be lifetime members of BitShares to run the bot

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

`JSON FORMAT`
{"type":"<MEMO OPTIONS>"}

`MEMO OPTIONS`
- client memo options
 - "three_months"
 - "six_months"
 - "twelve_months"
 - "stop"
- admin memo options (requires LTM account AND client being in MANAGER list)
 - "bmg_to_bittrex"
 - "bittrex_to_bmg"
 - "loan_to_bmg"

`FEES`
The bot charges a fee of 50 BTS and returns your funds if:
- sending invalid stake amount
- sending invalid memo
- sending admin request without being in MANAGER list
- sending admin loan_to_bmg without lifetime member (LTM) status on your account
- bot ignores bittrex to bmg and vice versa transfer requests if not LTM

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
        block_start INTEGER     # bitshares block number upon stake creation
        block_processed INTEGER # bitshares block number upon payment
        number INTEGER          # counting number for interest payments, eg 1,2,3,4...
    );
    CREATE TABLE receipts (
        nonce INTEGER           # munix start time of contract (same as 'stakes/start')
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

`
DISCUSSION
`
The stakeBTS is 2 listeners with withdrawal priviledges
communicating via sql database.
1) bitshares block operation listener:
    listens for new client stakes
        sends stake confirmation (withdrawal)
        inputs potential stake payouts to database
    listens for cancelled client stakes
        ends stakes prematurely paying principal less penalty (withdrawal)
        updates database accordingly and aborts further interest payments
2) payment due sql database listener:
    listens for pending items past due
    pays interest and principal on due time (withdrawal)
    if penalty becomes due its aborted

a client approaches bmg w/ a new stake the bot creates database rows
for every potential outcome of that stake;
there will always be 3 + number of months rows created.
contract_n, principal, penalty, interest, interest, interest, etc.
and interest payments will be numbered,
contract will always be for amount 1, and penalty will always be negative.
every payment, regardless of type, will have a due date upon creation...
contract is always due on day of creation.
principal and penalty are always due at close of contract.
interest is due in ascending 30 day periods.
for example a 100000 3 month contract has 6 lines

1) type=contract_3 amount=1 status=paid number=0
2) type=principal amount=100000 status=pending number=0
3) type=penalty amount=-15000 status=pending number=0
4) type=interest amount=8000 status=pending number=1
5) type=interest amount=8000 status=pending number=2
6) type=interest amount=8000 status=pending number=3

this is the stake rows of 3 month contract -
there are also additional columns for timestamps, etc...
but we'll skip them for now just to have discussion
so whether a new user approaches... or we put old contracts into the database...
if its a 3 month contract there are 6 db entries
(6 month contract has +3 entries and
12 month contract has +6 entries to account for additional interest payments)
in the case of new user...
as each pending item approaches its due date, it will be processed.

The bot (aside from being a block ops listener)
is also effectively a "database listener"
looking for status=pending where time due < now.

1) if interest becomes due its paid.
2) if the penalty comes due it is aborted and final principal+interest is paid.
3) if the user takes principal prior to due...

then pending interest are aborted
and the (negative) penalty is paid against the principal.
in the case of an existing "old" contract...
it is uploaded in the database the exact same way;
but automated/simulated by script to run through the text document containing them...
rather than via "block ops listener".
additionally... the import old data script goes in and overwrites the "pending" status
 on the 1st (or 1st and 2nd) interest payment to "paid"
 so that it does not get processed again by the main script.
it uses the number column in the database to update the correct payment
and marks them processed on june 30 or july 31 of this year
this happens once prior to the main script startup you'll have to run import_data.py
to build the initial database of old contracts. It

1) adds all line items for each old contract and
2) marks those already manually processed as paid.

then when you start running the main script full time...
the 3rd final payout of an old contract (some cases 2nd and 3rd)
will still be a pending item in the database to be processed.
It will either pay it as it comes due...
or if taken prematurely it will abort it
and return principal less penalty as it would with any other stake.

Once the main bot is running
it won't know the difference between old contracts and new.
it just sees "pending" vs "paid/aborted" line items

`RESET DATABASE`

- `rm stake_bitshares.db`
- `sqlite3 stake_bitshares.db`
- `.schema`
- `.quit`

`UNIT TESTING CHECKLIST`

# 1) BALANCES AND WITHDRAWALS
- in a seperate script import withdrawal and balances definitions:
- unit test `post_withdrawal_bittrex()` and `post_withdrawal_pybitshares()`
- unit test `get_balance_bittrex()` and `get_balance_pybitshares()`

# 2) BLOCK OPERATIONS LISTENER
- reset database
- in config.py set `DEV = True`
- send 0.1 BTS to broker, ensure script hears it arrive to the `BROKER` account.
- check state of `receipts` and `stakes` database tables

# 3) DATABASE LISTENER
- in config.py set `DEV = True`
- reset database
- load old contracts:
- - `python3.8 import_data.py`
- print database contents:
- - `sqlite3 stake_bitshares.db`
- - `SELECT * FROM stakes;`
- via sql, change the due date on a single payment to 0, see that it gets paid
- - `sqlite3 stake_bitshares.db`
- - `UPDATE stakes SET due=0 WHERE client='user1234' AND number=6;`
- check state of `receipts` and `stakes` database tables

# 4) REPLAY BLOCKS
- reset database
- in config.py set `DEV = True`
- in config.py test True, False, int() of `REPLAY`
- ensure script starts at correct block number
- script should not create duplicates in stakes database when replaying
- check state of `receipts` and `stakes` database tables

# 5) CLIENT AND ADMIN MEMOS
- reset database
- with config.py set `DEV = False` and `1000` added to the list of `INVEST_AMOUNTS`
- test login functionality
- send an invalid amount
- send an invalid memo
- send a valid amount `1000` and valid memo to start a new stake
- send signal to stop a stake
- using a `MANAGER` account test admin memos (with and without `LTM`)
 - `bmg_to_bittrex`
 - `bittrex_to_bmg`
 - `loan_to_bmg`
- check state of `receipts` and `stakes` database tables

`FEATURES`

- automatically move funds from bittrex to hot wallet to cover payments due
- does not allow non-ltm users to administrate
- allows replay from current block, last block in database, or user specified block.
- prevents double entries during replay

`WARNING`

This software is provided without warranty.
Automating withdrawals is inherently exploit prone.
Conduct an security review commensurate with your investment.

`SPONSOR`

This software is sponsored and managed by BitShares Management Group Limited
- www.bitshares.org

`LICENSE`

# WTFPL

`RELEASE STATUS`

# feature complete ALPHA - actively testing - peer review appreciated

`DEVELOPERS`

v1.0 initial prototype
- iamredbar: iamredbar@protonmail.com

v2.0 refactor, refinement, added features
- litepresence: finitestate@tutamail.com

