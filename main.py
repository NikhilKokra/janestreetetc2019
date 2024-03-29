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
import signal


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


# unrealized_portfolio = {"BOND": [], "VALBZ": [],
#                         "VALE": [], "GS": [], "MS": [], "WFC": [], "XLF": []}
not_acked_bonds = {}
pending_bond_orders = {}

# ~~~~~============== NETWORKING CODE ==============~~~~~


class Connection(object):
    def __init__(self, hostname,):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.hostname = hostname
        self.id = 0
        self.exchange = self.connect()
        self.holdings = self.hello()
        self.positions = {}
        self.conversions = {}
        self.composition = {
    "BOND": 3,
    "GS": 2, 
    "MS": 3,
    "WFC": 2
}
        self.book = {
    "BOND": {"best_bid": None, "best_ask": None},
    "VALBZ": {"best_bid": None, "best_ask": None},
    "VALE": {"best_bid": None, "best_ask": None},
    "GS": {"best_bid": None, "best_ask": None}, "MS": {"best_bid": None, "best_ask": None}, "WFC": {"best_bid": None, "best_ask": None}, "XLF": {"best_bid": None, "best_ask": None}
}
        for obj in self.holdings['symbols']:
            self.positions[obj["symbol"]] = obj["position"]

    def connect(self):
        if not test_mode:
            self.s.settimeout(1.0)
        self.s.connect((self.hostname, port))
        return self.s.makefile('rw', 1)

    def update_price(self, data):
        symbol = data['symbol']
        if len(data["buy"]) > 0:
            self.book[symbol]["best_bid"] = data["buy"][0]
        if len(data["sell"]) > 0:
            self.book[symbol]["best_ask"] = data["sell"][0]

    def hello(self):
        return self.request({"type": "hello", "team": team_name.upper()})

    def request(self, obj):
        self.write_to_exchange(obj)
        return self.read_process()
        #resp = self.read_from_exchange()
        #_update_bond_orders(resp)
        #return resp

    def write_to_exchange(self, obj):
        json.dump(obj, self.exchange)
        self.exchange.write("\n")

    def read_from_exchange(self):
        data = json.loads(self.exchange.readline())
        return data

    def read_process(self):
        data = self.read_from_exchange()
        if data['type'] == 'book':
            self.update_price(data)
        elif data['type'] == "fill":
            c = -1
            if data['dir'] == "BUY":
                c = 1
            self.positions[data['symbol']] += c*data['size']
            self.positions['USD'] -= c*data['size']*data['price']
        elif data['type'] == 'ack':
            if data['order_id'] in self.conversions:
                size = self.conversions[data['order_id']]['size']
                c = -1
                if self.conversions[data['order_id']]['side'] == "BUY":
                    c = 1
                if self.conversions[data['order_id']]['symbol'] == "XLF":
                    self.positions["XLF"] += c*size
                    for ticker in self.composition:
                        self.positions[ticker] -= c*(size//10)*self.composition[ticker]
                else:
                    self.positions["VALBZ"] += c*size
                    self.positions["VALE"] -= c*size
        return data

    def convert(self, symbol, side, size):
        print("CONVERTING %s %s %s" % (symbol, side, size))
        self.conversions[self.id]['symbol'] = symbol
        self.conversions[self.id]['side'] = side
        self.conversions[self.id]['size'] = size
        req = self.request({"type": "convert", "order_id": self.id, "symbol": symbol, "dir": side, "size": size})
        self.id += 1
        return req

    def add_ticker(self, symbol, side, price, size):
        print("%s %s $%s, %s shares" % (symbol, side, price, size))
        req = self.request({"type": "add", "order_id": self.id,
                            "symbol": symbol, "dir": side, "price": price, "size": size})
        self.id += 1
        return req


def adr(conn, valbz, vale, state):
    adr_bids = vale['best_bid']
    adr_asks = vale['best_ask']

    stock_bids = valbz['best_bid']
    stock_asks = valbz['best_ask']

    # arbitrage VALBZ buy
    if state == None and adr_bids[0] - stock_asks[0] > 10:
        quantity = min(stock_asks[1], adr_bids[1])
        conn.add_ticker("VALBZ", "BUY", stock_asks[0], quantity)
        return "valbzbuy"


    if state == "valbzbuy" and conn.positions["VALBZ"] != None and conn.positions["VALBZ"] > 0:
        conn.convert("VALBZ", "SELL", conn.positions["VALBZ"])
        return "valbzconvert"

    if state == "valbzconvert" and conn.positions["VALE"] != None and conn.positions["VALE"] > 0:
        conn.add_ticker("VALE", "SELL", adr_bids[0], conn.positions["VALE"])
        return None

    #arbitrage VALE buy
    if state == None and stock_bids[0] - adr_asks[0] > 10:
        quantity = min(stock_asks[1], adr_bids[1])
        conn.add_ticker("VALE", "BUY", adr_asks[0], quantity)
        return "valebuy"

    if state == "valebuy" and conn.positions["VALE"] != None and conn.positions["VALE"] > 0:
        conn.convert("VALE", "SELL", conn.positions["VALE"])
        return "valeconvert"

    if state == "valeconvert" and conn.positions["VALBZ"] != None and conn.positions["VALBZ"] > 0:
        conn.add_ticker("VALBZ", "SELL", adr_bids[0], conn.positions["VALBZ"])
        return None

    return None

limits = {
        'BOND': 100,
        "VALBZ": 10,
        "VALE":	10,
        "GS": 100,
        "MS": 100,
        "WFC": 100,
        "XLF": 100
}

def bonds_helper(conn, price, target, bond_orders_d, target_order):
    if price not in bond_orders_d:
        conn.add_ticker("BOND", target_order, price, target)
    elif bond_orders_d[price] < target:
        conn.add_ticker("BOND", target_order, price, target - bond_orders_d[price])

def bonds(conn):
    bond_orders = pending_bond_orders.values()
    bond_orders_d = dict([(a, b) for [a, b] in bond_orders])
    
    print()
    print()
    print()
    print()
    print(bond_orders)
    print(str(bond_orders_d))
    bonds_helper(conn, 995, 30, bond_orders_d, "BUY")
    bonds_helper(conn, 996, 25, bond_orders_d, "BUY")
    bonds_helper(conn, 997, 20, bond_orders_d, "BUY")
    bonds_helper(conn, 998, 15, bond_orders_d, "BUY")
    bonds_helper(conn, 999, 10, bond_orders_d, "BUY")
    bonds_helper(conn, 1001, 10, bond_orders_d, "SELL")
    bonds_helper(conn, 1002, 15, bond_orders_d, "SELL")
    bonds_helper(conn, 1003, 20, bond_orders_d, "SELL")
    bonds_helper(conn, 1004, 25, bond_orders_d, "SELL")
    bonds_helper(conn, 1005, 30, bond_orders_d, "SELL")

# ~~~~~============== MAIN LOOP ==============~~~~~

last_prices = {
    "BOND": {"best_bid": None, "best_ask": None},
    "VALBZ": {"best_bid": None, "best_ask": None},
    "VALE": {"best_bid": None, "best_ask": None},
    "GS": {"best_bid": None, "best_ask": None}, "MS": {"best_bid": None, "best_ask": None}, "WFC": {"best_bid": None, "best_ask": None}, "XLF": {"best_bid": None, "best_ask": None}
}
last_n = 15


def update_price(conn, data):
    symbol = data['symbol']
    if len(data["buy"]) > 0:
        last_prices[symbol]["best_bid"] = data["buy"][0]
    if len(data["sell"]) > 0:
        last_prices[symbol]["best_ask"] = data["sell"][0]


composition = {
    "BOND": 3,
    "GS": 2,
    "MS": 3,
    "WFC": 2
}

conversion_fee = 100
# condition: add up all composing < 10*xlf


def etf(conn, data):
    sellingPriceComposed = 0
    buyingPriceComposed = 0
    for key in [key for key in composition] + ["XLF"]:
        if conn.book[key]['best_bid'] is None:
            return 
    for key in composition:
        sellingPriceComposed += composition[key]*conn.book[key]['best_bid'][0]
        buyingPriceComposed += composition[key]*conn.book[key]['best_ask'][0]
    buyingXLF = conn.book["XLF"]['best_ask']
    sellingXLF = conn.book["XLF"]['best_bid']
    print(buyingXLF)
    buyingPriceXLF = buyingXLF[0]
    sellingPriceXLF = sellingXLF[0]
    if buyingPriceComposed + conversion_fee < 10*sellingPriceXLF:
        min_converts = 1000000000000000000000000000000
        for ticker in composition:
            min_converts = min(conn.book[ticker]['best_ask'][1]//composition[ticker], min_converts)
        min_converts = min(sellingXLF[1], min_converts)
        for i in range(min_converts):
            for key in composition:
                conn.add_ticker(key, "BUY", conn.book[key]['best_ask'][0], composition[key])
            conn.convert("XLF", "BUY", 10)
            conn.add_ticker("XLF", "SELL", sellingXLF[0], 10)
    elif 10*buyingPriceXLF + conversion_fee < sellingPriceComposed:
        min_converts = 1000000000000000000000000000000
        for ticker in composition:
            min_converts = min(conn.book[ticker]['best_bid'][1]//composition[ticker], min_converts)
        min_converts = min(buyingXLF[1], min_converts)
        for i in range(min_converts):
            conn.add_ticker("XLF", "BUY", buyingXLF[0], 10)
            conn.convert("XLF", "SELL", 10)
            for key in composition:
                conn.add_ticker(key, "SELL", conn.book[key]['best_bid'][0], composition[key])


def main():
    conn = Connection(exchange_hostname)
    done = False
    adrstate = None
    while True:
        # A common mistake people make is to call write_to_exchange() > 1
        # time for every read_from_exchange() response.
        # Since many write messages generate marketdata, this will cause an
        # exponential explosion in pending messages. Please, don't do that!
        
        try:
            data = conn.read_process()
            #etf(conn, data)
            #bonds(conn)

            if conn.book["VALBZ"]["best_bid"] is not None and conn.book["VALE"]["best_bid"] is not None:
                if adrstate == "valbzconvert" or adrstate == "valeconvert":
                    adrstate = adr(conn, conn.book["VALBZ"], conn.book["VALE"], adrstate)
                    if adrstate == None:
                        print("--------------------")
                        print("--------------------")
                        print("COMPLETED ARBITRAGE")
                        print("--------------------")
                        print("--------------------")
                else:
                    adrstate = adr(conn, conn.book["VALBZ"], conn.book["VALE"], adrstate)
        except Exception as e:
            print("somtehign abf happened ")
            print(e)
            sys.exit(1)



if __name__ == "__main__":
    main()
