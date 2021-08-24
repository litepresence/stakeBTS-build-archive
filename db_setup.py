"""
BitShares.org StakeMachine
Create an Empty Database with Correct Schema
BitShares Management Group Co. Ltd.
"""

from sqlite3 import connect as sql
from config import DB

con = sql(DB)
cur = con.cursor()
query = """
CREATE TABLE block_num (block_num INTEGER);
"""
cur.execute(query)
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
    client, type, number, block_start
    ) ON CONFLICT IGNORE
);
"""
cur.execute(query)
query = """
CREATE TABLE receipts (
    nonce INTEGER,
    now INTEGER,
    msg TEXT
);
"""
cur.execute(query)
query = """
INSERT INTO block_num (block_num) VALUES (61000000);
"""
cur.execute(query)
con.commit()
con.close()
