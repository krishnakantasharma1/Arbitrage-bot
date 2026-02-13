import os
import time
from binance.client import Client
from binance.enums import *

# =====================
# LOAD ENV VARIABLES
# =====================

API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")

SYMBOL = os.getenv("COIN", "OM").upper() + "USDT"
TOTAL_USDT = float(os.getenv("USDT", "10"))
ENTRY_SPREAD = float(os.getenv("ENTRY_SPREAD", "0"))
EXIT_SPREAD = float(os.getenv("EXIT_SPREAD", "1"))

CHECK_INTERVAL = 2

client = Client(API_KEY, API_SECRET)

position_open = False
qty = 0

# =====================
# GET PRICES
# =====================

def get_prices():
    spot = float(client.get_symbol_ticker(symbol=SYMBOL)["price"])
    futures = float(client.futures_symbol_ticker(symbol=SYMBOL)["price"])
    return spot, futures

# =====================
# CALCULATE SPREAD
# =====================

def get_spread():
    spot, futures = get_prices()
    spread = (futures - spot) / spot * 100
    return spread, spot, futures

# =====================
# EXECUTE ENTRY
# =====================

def enter():
    global position_open, qty

    spot_price, futures_price = get_prices()

    qty = TOTAL_USDT / spot_price

    print("Entering hedge position")

    client.order_market_buy(
        symbol=SYMBOL,
        quantity=qty
    )

    client.futures_create_order(
        symbol=SYMBOL,
        side=SIDE_SELL,
        type=ORDER_TYPE_MARKET,
        quantity=qty
    )

    position_open = True

# =====================
# EXIT POSITION
# =====================

def exit():
    global position_open

    print("Closing hedge position")

    client.order_market_sell(
        symbol=SYMBOL,
        quantity=qty
    )

    client.futures_create_order(
        symbol=SYMBOL,
        side=SIDE_BUY,
        type=ORDER_TYPE_MARKET,
        quantity=qty
    )

    position_open = False

# =====================
# MAIN LOOP
# =====================

print("Bot started")
print("Symbol:", SYMBOL)
print("USDT:", TOTAL_USDT)
print("Entry spread:", ENTRY_SPREAD)
print("Exit spread:", EXIT_SPREAD)

while True:

    try:

        spread, spot, futures = get_spread()

        print(f"Spread: {spread:.3f}%")

        if not position_open:

            if ENTRY_SPREAD == 0 or spread >= ENTRY_SPREAD:
                enter()

        else:

            if spread <= EXIT_SPREAD:
                exit()

        time.sleep(CHECK_INTERVAL)

    except Exception as e:
        print("Error:", e)
        time.sleep(5)
