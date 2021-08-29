"""
BitShares.org StakeMachine
Unit Test to abuse database race condition
BitShares Management Group Co. Ltd.
"""

# STANDARD PYTHON MODULES
import time
from random import randint, random
from threading import Thread

# STAKE BTS MODULES
from stake_bitshares import get_block_num_database, set_block_num_database


def abuse():
    """
    repeatedly get and set block number in the db
    """
    for _ in range(20):
        time.sleep(0.01 * random())
        if random() > 0.5:
            num = randint(100, 999)
            set_block_num_database(num)
            print("set", num)
        else:
            print("get", get_block_num_database())


def main():
    """
    spin off several threads to induce SQL race condition
    """
    print("\033c")
    print("you should see occassional OperationalError")
    print("but get and set should continue\n")
    input("press Enter to begin\n")
    threads = {}
    for i in range(100):
        threads[i] = Thread(target=abuse)
    for i in range(100):
        threads[i].start()


if __name__ == "__main__":
    main()
