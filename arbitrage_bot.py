import time
import sys
import os
from binance.client import Client
from binance.enums import *

API_KEY = "3KGa3klZtYV4ETszh1xIWBZTvOKrhxuJ907OvxJKuu0CcgpTVOcdr9gpGYAUoNRc"
API_SECRET = "1VzwntpWSQUiq57AUq8VIGSXWok6GIO8vZbPmvE6i9iwvuqiH3DrR5zI4Ca3pqzy"

client = Client(API_KEY, API_SECRET)

CHECK_INTERVAL = 0.3
MIN_VOLUME = 5000000
MAX_SLIPPAGE = 0.5  # percent

symbol = ""
exit_target = 0
position_open = False

entry_spot_price = 0
entry_futures_price = 0
entry_qty = 0


# ==========================
# ALERT
# ==========================

def beep():
    print("\a", end="", flush=True)


# ==========================
# BALANCE CHECK
# ==========================

def get_spot_usdt():
    balances = client.get_account()["balances"]
    for b in balances:
        if b["asset"] == "USDT":
            return float(b["free"])
    return 0


def get_futures_usdt():
    balances = client.futures_account()["assets"]
    for b in balances:
        if b["asset"] == "USDT":
            return float(b["availableBalance"])
    return 0


# ==========================
# SPREAD (ORDER BOOK BASED)
# ==========================

def get_spread(sym):

    spot_book = client.get_order_book(symbol=sym, limit=5)
    futures_book = client.futures_order_book(symbol=sym, limit=5)

    spot_ask = float(spot_book["asks"][0][0])
    spot_bid = float(spot_book["bids"][0][0])

    futures_bid = float(futures_book["bids"][0][0])
    futures_ask = float(futures_book["asks"][0][0])

    reverse_spread = ((futures_bid - spot_ask) / spot_ask) * 100
    positive_spread = ((futures_ask - spot_bid) / spot_bid) * 100

    if abs(reverse_spread) >= abs(positive_spread):
        return reverse_spread, abs(reverse_spread), "reverse", spot_ask, futures_bid
    else:
        return positive_spread, abs(positive_spread), "positive", spot_bid, futures_ask


# ==========================
# VOLUME CHECK
# ==========================

def check_volume(sym):

    vol = float(client.futures_ticker(symbol=sym)["quoteVolume"])

    print(f"Volume: {vol:.0f}")

    if vol < MIN_VOLUME:
        print("Unsafe liquidity")
        return False

    return True


# ==========================
# LEVERAGE
# ==========================

def setup_futures(sym):

    try:
        client.futures_change_margin_type(
            symbol=sym,
            marginType="CROSSED"
        )
    except:
        pass

    client.futures_change_leverage(
        symbol=sym,
        leverage=1
    )

    print("Futures set to Cross, 1x leverage")


# ==========================
# SAFE ENTRY
# ==========================

def safe_enter(sym, total_usdt):

    global position_open
    global entry_spot_price
    global entry_futures_price
    global entry_qty

    spot_balance = get_spot_usdt()
    futures_balance = get_futures_usdt()

    half = total_usdt / 2

    if spot_balance < half or futures_balance < half:
        print("Insufficient balance")
        return False

    spread, abs_spread, direction, spot_price, futures_price = get_spread(sym)

    spot_qty = half / spot_price
    futures_qty = half / futures_price

    print(f"Entering hedge | Spread {abs_spread:.2f}%")

    try:

        if direction == "reverse":

            spot_order = client.order_market_buy(
                symbol=sym,
                quoteOrderQty=half
            )

            futures_order = client.futures_create_order(
                symbol=sym,
                side=SIDE_SELL,
                type="MARKET",
                quantity=round(futures_qty, 3)
            )

        else:

            spot_order = client.order_market_sell(
                symbol=sym,
                quantity=round(spot_qty, 3)
            )

            futures_order = client.futures_create_order(
                symbol=sym,
                side=SIDE_BUY,
                type="MARKET",
                quantity=round(futures_qty, 3)
            )

    except Exception as e:

        print("Entry failed:", e)
        return False

    # Verify execution

    if spot_order["status"] != "FILLED":
        print("Spot not filled")
        return False

    if futures_order["status"] != "FILLED":
        print("Futures not filled — rolling back")

        client.order_market_sell(
            symbol=sym,
            quantity=round(spot_qty, 3)
        )

        return False

    entry_spot_price = spot_price
    entry_futures_price = futures_price
    entry_qty = futures_qty

    position_open = True

    print("Hedge entered safely")

    beep()

    return True


# ==========================
# SAFE EXIT
# ==========================

def safe_exit(sym):

    global position_open

    print("Closing hedge")

    asset = sym.replace("USDT","")

    balances = client.get_account()["balances"]

    for b in balances:

        if b["asset"] == asset:

            qty = float(b["free"])

            if qty > 0:

                client.order_market_sell(
                    symbol=sym,
                    quantity=qty
                )

    pos = client.futures_position_information(symbol=sym)[0]

    qty = abs(float(pos["positionAmt"]))

    if qty > 0:

        side = SIDE_BUY if pos["positionAmt"].startswith("-") else SIDE_SELL

        client.futures_create_order(
            symbol=sym,
            side=side,
            type="MARKET",
            quantity=qty
        )

    position_open = False

    print("Exit complete")

    beep()


# ==========================
# PROFIT
# ==========================

def get_profit(sym):

    pos = client.futures_position_information(symbol=sym)[0]

    futures_pnl = float(pos["unRealizedProfit"])

    spot_price = float(client.get_symbol_ticker(symbol=sym)["price"])

    spread_profit = (spot_price - entry_spot_price) * entry_qty

    total = spread_profit + futures_pnl

    return spread_profit, futures_pnl, total


# ==========================
# MONITOR
# ==========================

def monitor(sym):

    global exit_target

    while position_open:

        spread, abs_spread, direction, spot_price, futures_price = get_spread(sym)

        spread_profit, futures_pnl, total = get_profit(sym)

        print(
            f"Spread {abs_spread:.2f}% | "
            f"SpreadProfit {spread_profit:.4f} | "
            f"FuturesPnL {futures_pnl:.4f} | "
            f"TOTAL {total:.4f}"
        )

        if abs_spread <= exit_target:

            safe_exit(sym)
            print(f"Final profit: {total:.4f}")

            break

        time.sleep(CHECK_INTERVAL)


# ==========================
# MAIN
# ==========================

def main():

    global symbol
    global exit_target

    coin = input("Coin: ").upper()

    symbol = coin + "USDT"

    total = float(input("Total USDT: "))

    entry = input("Entry spread (blank instant): ")

    exit_target = float(input("Exit spread: "))

    setup_futures(symbol)

    if not check_volume(symbol):
        return

    if entry == "":

        if not safe_enter(symbol, total):
            return

    else:

        entry = float(entry)

        while True:

            spread, abs_spread, direction, spot_price, futures_price = get_spread(symbol)

            print(f"Spread {abs_spread:.2f}%")

            if abs_spread >= entry:

                if safe_enter(symbol, total):
                    break

            time.sleep(CHECK_INTERVAL)

    monitor(symbol)


main()
