"""
BitShares.org StakeMachine
Create an Empty Database with Correct Schema
BitShares Management Group Co. Ltd.
"""

# STANDARD PYTHON MODULES
import os
from subprocess import call
from sys import version as python_version

# STAKE BTS MODULES
from config import DB
from utilities import it, sql_db

# GLOBAL CONSTANTS
PATH = os.path.dirname(os.path.abspath(__file__)) + "/database"

def main():
    """
    delete any existing db and initialize new SQL db
    """
    # ensure the correct python version
    if float(".".join(python_version.split(".")[:2])) < 3.8:
        raise AssertionError("stakeBTS Requires Python 3.8+")
    # create database folder
    os.makedirs(PATH, exist_ok=True)
    # user input w/ warning
    print("\033c")
    print(it("red", "WARNING THIS SCRIPT WILL RESTART DATABASE AND ERASE ALL DATA\n"))
    choice = input("Erase database? y + Enter to continue or Enter to cancel\n")
    # erase and recreate db
    if choice == "y":
        command = "rm database/stake_bitshares.db"
        print("\033c", it("red", command), "\n")
        call(command.split())
        print("creating sqlite3:", it("green", DB), "\n")
        # batch database creation queries and process atomically
        queries = []
        # block number table
        query = """
        CREATE TABLE block_num (block_num INTEGER);
        """
        dml = {"query": query, "values": ()}
        queries.append(dml)
        # stakes table
        query = """
        CREATE TABLE stakes (
            client TEXT,
            token TEXT,
            amount INTEGER,
            type TEXT,
            start INTEGER,
            due INTEGER,
            processed INTEGER,
            status TEXT,
            block_start INTEGER,
            block_processed INTEGER,
            number INTEGER,
            UNIQUE (
            client, type, number, block_start, start
            ) ON CONFLICT IGNORE
        );
        """
        dml = {"query": query, "values": ()}
        queries.append(dml)
        # receipts table
        query = """
        CREATE TABLE receipts (
            nonce INTEGER,
            now INTEGER,
            msg TEXT
        );
        """
        dml = {"query": query, "values": ()}
        queries.append(dml)
        # starting block number table
        query = """
        INSERT INTO block_num (block_num) VALUES (?);
        """
        values = (61000000,)
        dml = {"query": query, "values": values}
        queries.append(dml)
        sql_db(queries)
        # display the tables' info
        query = """
        PRAGMA table_info (stakes)
        """
        for col in sql_db(query):
            print(col)
        query = """
        PRAGMA table_info (receipts)
        """
        for col in sql_db(query):
            print(col)
        query = """
        PRAGMA table_info (block_num)
        """
        for col in sql_db(query):
            print(col)



if __name__ == "__main__":
    main()
