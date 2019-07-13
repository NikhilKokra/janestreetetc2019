#!/usr/bin/python

# ~~~~~==============   HOW TO RUN   ==============~~~~~
# 1) Configure things in CONFIGURATION section
# 2) Change permissions: chmod +x bot.py
# 3) Run in loop: while true; do ./bot.py; sleep 1; done

from __future__ import print_function

import sys
import socket
import json
import time
import os
import random

id = 0

# ~~~~~============== CONFIGURATION  ==============~~~~~
# replace REPLACEME with your team name!
team_name = "cablecar"
# This variable dictates whether or not the bot is connecting to the prod
# or test exchange. Be careful with this switch!
test_mode = os.environ.get("TYPE") != "production"

if not test_mode:
    print("running in production.....")

# This setting changes which test exchange is connected to.
# 0 is prod-like
# 1 is slower
# 2 is empty
test_exchange_index = 2
prod_exchange_hostname = "production"

port = 25000 + (test_exchange_index if test_mode else 0)
exchange_hostname = "test-exch-" + \
    team_name if test_mode else prod_exchange_hostname

bonds = {}

# ~~~~~============== NETWORKING CODE ==============~~~~~


class Connection(object):
    def __init__(self, hostname,):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.hostname = hostname
        self.id = 0
        self.exchange = self.connect()

    def connect(self):
        self.s.connect((self.hostname, port))
        return self.s.makefile('rw', 1)

    def request(self, obj):
        self.write_to_exchange(obj)
        return self.read_from_exchange()

    def write_to_exchange(self, obj):
        json.dump(obj, self.exchange)
        self.exchange.write("\n")

    def read_from_exchange(self):
        data = json.loads(self.exchange.readline())
        if data["type"] == "error":
            raise Exception("Server returned error: %s" % data["error"])
        return data
    
    def add_ticker(self, symbol, side, price, size):
        self.id += 1
        return self.request({"type": "add", "order_id": self.id, "symbol": symbol, "dir": side, "price": price, "size": size})

def adr(conn, valbz, vale):
    global id
    adr_bids = vale['bids']
    adr_asks = vale['asks']

    stock_bids = valbz['bids']
    stock_asks = valbz['asks']

    adr_midpoints = []
    for i in range(len(adr_bids)):
        adr_midpoints += [(adr_asks[i] + adr_bids[i]) / 2]

    stock_midpoints = []
    for i in range(len(stock_bids)):
        stock_midpoints += [(stock_asks[i] + stock_bids[i]) / 2]

    largest_diff = ((max(stock_midpoints) - min(adr_midpoints)) + (max(adr_midpoints) - min(stock_midpoints))) / 2
    adr_avg = sum(adr_midpoints) / len(adr_midpoints)
    stock_avg = sum(stock_midpoints) / len(stock_midpoints)

    threshold = largest_diff * .1

    if adr_bids[-1] - stock_avg > threshold:
        #place market sell order

        print("PLACING MARKET SELL ORDER ADR")

        for _ in range(10):
            id += 1
            conn.write_to_exchange(
                {"type": "add", "order_id": id, "symbol": "VALE", "dir": "SELL", "price": adr_bids[-1],"size": 1})

    if stock_avg - adr_asks[-1] > threshold:
        #place market buy order

        print("PLACING MARKET BUY ORDER ADR")

        for _ in range(10):
            id += 1
            conn.write_to_exchange(
                {"type": "add", "order_id": id, "symbol": "VALE", "dir": "BUY", "price": adr_asks[-1],"size": 1})





def bonds(conn, data = None):
    global id
    i = 0
    for i in range(0, 5):
        conn.write_to_exchange({"type": "add", "order_id": id, "symbol": "BOND", "dir": "BUY", "price": (1000 - random.randint(1,6)), "size": 10})
        id += 1
        conn.write_to_exchange({"type": "add", "order_id": id, "symbol": "BOND", "dir": "SELL", "price": (1000 + random.randint(1,6)), "size": 10})
        id += 1

# ~~~~~============== MAIN LOOP ==============~~~~~

def main():
    fair_values = {"BOND": 1000, "VALBZ": 0, "VALE": 0,
                   "GS": 0, "MS": 0, "WFC": 0, "XLF": 0}
    conn = Connection(exchange_hostname)
    conn.write_to_exchange(
        {"type": "hello", "team": team_name.upper()})
    hello_from_exchange = conn.read_from_exchange()
    print("The exchange replied:", hello_from_exchange, file=sys.stderr)

    while True:
        data = conn.read_from_exchange()
        # A common mistake people make is to call write_to_exchange() > 1
        # time for every read_from_exchange() response.
        # Since many write messages generate marketdata, this will cause an
        # exponential explosion in pending messages. Please, don't do that!

        print(data)
        try:
            bonds(conn)
        except Exception as e:

            conn = Connection(exchange_hostname)
            print("bonds didnt work")
            print(e)

        time.sleep(.5)



if __name__ == "__main__":
    main()


