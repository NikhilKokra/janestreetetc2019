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
import pprint

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
test_exchange_index = 1
prod_exchange_hostname = "production"

port = 25000 + (test_exchange_index if test_mode else 0)
exchange_hostname = "test-exch-" + \
    team_name if test_mode else prod_exchange_hostname

# ~~~~~============== NETWORKING CODE ==============~~~~~


class Connection(object):
    def __init__(self, hostname,):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.hostname = hostname
        self.id = 0
        self.exchange = self.connect()
        self.holdings = self.hello()

    def connect(self):
        self.s.connect((self.hostname, port))
        return self.s.makefile('rw', 1)

    def hello(self):
        return self.request({"type": "hello", "team": team_name.upper()})

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

    def convert(self, symbol, side, size):
        print("CONVERTING %s %s %s" % (symbol, side, size))
        req = self.request({"type": "convert", "order_id": self.id, "symbol": symbol, "dir": side, "size": size})
        self.id += 1
        return req


    def add_ticker(self, symbol, side, price, size):
        print("%s %s $%s, %s shares" % (symbol, side, price, size))
        req = self.request({"type": "add", "order_id": self.id, "symbol": symbol, "dir": side, "price": price, "size": size})
        self.id += 1
        return req


def adr(conn, valbz, vale):
    global id
    adr_bids = vale['best_bid']
    adr_asks = vale['best_ask']

    stock_bids = valbz['best_bid']
    stock_asks = valbz['best_ask']

    adr_midpoints = []
    for i in range(len(adr_bids)):
        adr_midpoints += [(adr_asks[i][0] + adr_bids[i][0]) / 2]

    stock_midpoints = []
    for i in range(len(stock_bids)):
        stock_midpoints += [(stock_asks[i][0] + stock_bids[i][0]) / 2]

    largest_diff = ((max(stock_midpoints) - min(adr_midpoints)) +
                    (max(adr_midpoints) - min(stock_midpoints))) / 2
    adr_avg = sum(adr_midpoints) / len(adr_midpoints)
    stock_avg = sum(stock_midpoints) / len(stock_midpoints)

    threshold = largest_diff * .3

    print(str(adr_midpoints))
    print(str(adr_bids))
    print(str(largest_diff))

    print("threshold " + str(threshold))
    print("adr best bid " + str(adr_bids[-1][0]))
    print("adr best ask " + str(adr_asks[-1][0]))
    print("stock avg " + str(stock_avg))

    if adr_bids[-1][0] - stock_avg > threshold:
        # place market sell order

        print("PLACING MARKET SELL ORDER ADR")

        id += 1
        conn.write_to_exchange(
            {"type": "add", "order_id": id, "symbol": "VALE", "dir": "SELL", "price": adr_bids[-1][0], "size": 4})
        conn.read_from_exchange()

        return True

    if stock_avg - adr_asks[-1][0] > threshold:
        # place market buy order

        print("PLACING MARKET BUY ORDER ADR")

        id += 1
        conn.write_to_exchange(
            {"type": "add", "order_id": id, "symbol": "VALE", "dir": "BUY", "price": adr_asks[-1][0], "size": 4})
        conn.read_from_exchange()

        return True

    return False


def bonds(conn, data=None):
    global id
    for i in range(0, 5):
        resp = conn.request({"type": "add", "order_id": id, "symbol": "BOND",
                             "dir": "BUY", "price": (1000 - random.randint(1, 6)), "size": 10})
        print(resp)
        id += 1
        resp = conn.request({"type": "add", "order_id": id, "symbol": "BOND",
                             "dir": "SELL", "price": (1000 + random.randint(1, 6)), "size": 10})
        print(resp)
        id += 1

# ~~~~~============== MAIN LOOP ==============~~~~~


last_prices = {
    "BOND": {"best_bid": [], "best_ask": []},
    "VALBZ": {"best_bid": [], "best_ask": []},
    "VALE": {"best_bid": [], "best_ask": []},
    "GS": {"best_bid": [], "best_ask": []}, "MS": {"best_bid": [], "best_ask": []}, "WFC": {"best_bid": [], "best_ask": []}, "XLF": {"best_bid": [], "best_ask": []}
}
last_n = 15


def _update_price_bid(price, symbol, lst):
    if len(lst) >= last_n:
        lst.pop(0)
    lst.append(price)
    last_prices[symbol]["best_bid"] = lst


def _update_price_ask(price, symbol, lst):
    if len(lst) >= last_n:
        lst.pop(0)
    lst.append(price)
    last_prices[symbol]["best_ask"] = lst


def update_price(conn, data):
    print(data)
    symbol = data['symbol']
    bid = last_prices[symbol]['best_bid']
    ask = last_prices[symbol]['best_ask']
    if len(data["buy"]) > 0:
        _update_price_bid(data["buy"][0], symbol, bid)
    if len(data["sell"]) > 0:
        _update_price_ask(data["sell"][0], symbol, bid)

composition = {
    "BOND": 3,
    "GS": 2, 
    "MS": 3,
    "WFC": 2
}

conversion_fee = 100
#condition: add up all composing < 10*xlf

def etf(conn, data):
    sellingPriceComposed = 0
    buyingPriceComposed = 0
    for key in composition:
        sellingPriceComposed += composition[key]*last_prices[key]['best_bid'][-1][0]
        buyingPriceComposed += composition[key]*last_prices[key]['best_ask'][-1][0]
    buyingXLF = last_prices["XLF"]['best_ask'][-1]
    sellingXLF = last_prices["XLF"]['best_bid'][-1]
    buyingPriceXLF = buyingXLF[0]
    sellingPriceXLF = sellingXLF[0]
    if buyingPriceComposed + conversion_fee < 10*sellingPriceXLF:
        min_converts = 1000000000000000000000000000000
        for ticker in composition:
            min_converts = min(last_prices[ticker]['best_ask'][-1][1]//composition[ticker], min_converts)
        min_converts = min(sellingXLF[1], min_converts)
        for i in range(min_converts):
            for key in composition:
                conn.add_ticker(key, "BUY", last_prices[key]['best_ask'][-1][0], compositon[key])
            conn.convert("XLF", "BUY", 1)
            conn.add_ticker("XLF", "SELL", sellingXLF[0], 10)
    else if 10*buyingPriceXLF + conversion_fee < sellingPriceComposed:
        min_converts = 1000000000000000000000000000000
        for ticker in composition:
            min_converts = min(last_prices[ticker]['best_bid'][-1][1]//composition[ticker], min_converts)
        min_converts = min(buyingXLF[1], min_converts)
        for i in range(min_converts):
            conn.add_ticker("XLF", "BUY", buyingXLF[0], 1)
            conn.convert("XLF", "SELL", 1)
            for key in composition:
                conn.add_ticker(key, "SELL", last_prices[key]['best_bid'][-1][0], compositon[key])


def main():
    conn = Connection(exchange_hostname)

    adr_iter = 0

    while True:
        # A common mistake people make is to call write_to_exchange() > 1
        # time for every read_from_exchange() response.
        # Since many write messages generate marketdata, this will cause an
        # exponential explosion in pending messages. Please, don't do that!
        adr_iter += 1
        try:
            data = conn.read_from_exchange()
            print("---DATA---")
            print(data)
            if data['type'] == 'book':
                update_price(conn, data)
                bonds(conn, data)
                #etf(conn, data)

            if len(last_prices["VALE"]["best_bid"]) > 1 and len(last_prices["VALBZ"]["best_bid"]) > 10 and adr_iter > 0:
                print("--------------")
                print()
                print("CALLED ADR")
                print()
                print("--------------")
                if adr(conn, last_prices["VALBZ"], last_prices["VALE"]):
                    adr_iter = -20

        except Exception as e:
            print("bonds didnt work")
            print(e)
            sys.exit(1)

        time.sleep(.5)


if __name__ == "__main__":
    main()
