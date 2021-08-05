
## StakeBTS Python Bot

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

`NOTES`


**Account that you wish to use for the bot must be imported with all 3 private keys:**
**(Owner, Active and Memo) into uptick.**

**On BOT start you will be asked to enter your uptick WALLET password**

**Bittrex api is used for outbound payments.**
**You must also have Bittrex API key/secret.**

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
                mark paid/aborted in database as applicable

`JSON FORMAT`
{"type":"<LENGTH_OF_STAKE>"}

`LENGTH_OF_STAKE`
- "three_months"
- "six_months"
- "twelve_months"
- "stop"

This software is sponsored and managed by BitShares Management Group Limited

