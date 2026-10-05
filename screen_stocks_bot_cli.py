"""
Screen Stocks trading bot - command-line menu version (official mod folders only).

Run:  python screen_stocks_bot_cli.py
Everything is controlled by typing the numbers shown in the menus.
Settings are saved to screen_stocks_bot_config.json next to this script.

The bot NEVER trades $BANK or $BASE (internal id: $PLAIN). This is hard-coded
and cannot be switched on from the menus.
"""
import json
import statistics
import sys
import time
from pathlib import Path

CONFIG_FILE = Path(__file__).with_name("screen_stocks_bot_config.json")

# Hard block. Matches on stock id AND display name, ignoring "$" and case.
# ($PLAIN is the id the game uses for the stock displayed as $BASE.)
BLOCKED = {"BANK", "BASE", "PLAIN"}

DEFAULTS = {
    "export_dir": "",
    "commands_dir": "",
    "dry_run": True,
    "stocks": [],          # empty list = every unlocked, non-blocked stock
    "lookback": 120,       # samples (~seconds) for the average
    "min_samples": 60,
    "entry_z": 2.0,        # how far from average before opening a trade
    "exit_z": 0.3,         # close when back within this of the average
    "trade_percent": 10,   # percent sent with buy / short
    "stop_loss": 20.0,     # close if a position moves this % against us
    "min_price": 1.0,      # ignore stocks cheaper than this
    "poll_seconds": 1.0,
}


# ------------------------------------------------------------------ blocking
def is_blocked(stock_id: str, name: str = "") -> bool:
    for value in (stock_id, name):
        if value and value.strip().lstrip("$").upper() in BLOCKED:
            return True
    return False


# ------------------------------------------------------------------- config
def load_config() -> dict:
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.loads(CONFIG_FILE.read_text()))
    except (OSError, json.JSONDecodeError):
        pass
    cfg["stocks"] = [s for s in cfg["stocks"] if not is_blocked(s)]
    return cfg


def save_config(cfg: dict):
    try:
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
    except OSError as e:
        print(f"  (could not save settings: {e})")


# ------------------------------------------------------------- input helpers
def ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        sys.exit(0)


def ask_choice(prompt: str, valid: set[int]) -> int:
    while True:
        raw = ask(prompt)
        if raw.isdigit() and int(raw) in valid:
            return int(raw)
        print("  Please type one of the numbers shown.")


def ask_number(label: str, current, cast=float, lo=None, hi=None):
    while True:
        raw = ask(f"  New value for {label} (now {current}, blank = keep): ")
        if raw == "":
            return current
        try:
            val = cast(raw)
        except ValueError:
            print("  That is not a number.")
            continue
        if (lo is not None and val < lo) or (hi is not None and val > hi):
            print(f"  Must be between {lo} and {hi}.")
            continue
        return val


def ask_folder(label: str, current: str) -> str:
    while True:
        raw = ask(f"  {label} folder (now: {current or 'not set'}, blank = keep): ").strip('"')
        if raw == "":
            return current
        if Path(raw).is_dir():
            return raw
        print("  That folder does not exist.")


# ------------------------------------------------------------- file helpers
def read_json(path: Path, retries: int = 5):
    """The game rewrites these files constantly, so retry on partial reads."""
    for _ in range(retries):
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            time.sleep(0.1)
    return None


def num(x) -> float:
    return float(x) if x not in (None, "") else 0.0   # shares/cash arrive as strings


def folders_ok(cfg: dict) -> bool:
    return bool(cfg["export_dir"]) and bool(cfg["commands_dir"]) \
        and Path(cfg["export_dir"]).is_dir() and Path(cfg["commands_dir"]).is_dir()


# ----------------------------------------------------------------- strategy
def zscore(prices: list[float], cfg: dict):
    window = prices[-int(cfg["lookback"]):]
    if len(window) < cfg["min_samples"]:
        return None
    sd = statistics.pstdev(window)
    if sd == 0:
        return None
    return (window[-1] - statistics.fmean(window)) / sd


def decide(cfg, price, z, pos, now_ms, player, available):
    owned = num(pos.get("sharesOwned"))
    shorted = num(pos.get("sharesShorted"))
    buy_ready = now_ms >= player.get("nextBuyAtMs", 0)
    short_ready = now_ms >= player.get("nextShortAtMs", 0)
    stop = cfg["stop_loss"] / 100.0

    if owned > 0:                                   # manage an existing long
        avg = pos.get("averageBuyPrice") or 0
        if avg > 1.0 and price < avg * (1 - stop):
            return ("sell", None, "stop-loss")
        if z >= -cfg["exit_z"]:
            return ("sell", None, f"back to average (z={z:.2f})")
        return None

    if shorted > 0:                                 # manage an existing short
        avg = pos.get("averageShortPrice") or 0
        if avg > 0 and price > avg * (1 + stop):
            return ("cover", None, "stop-loss")
        if z <= cfg["exit_z"]:
            return ("cover", None, f"back to average (z={z:.2f})")
        return None

    if z <= -cfg["entry_z"] and buy_ready and available > 0:
        return ("buy", cfg["trade_percent"], f"cheap (z={z:.2f})")
    if z >= cfg["entry_z"] and short_ready:
        return ("short", cfg["trade_percent"], f"expensive (z={z:.2f})")
    return None


# ------------------------------------------------------------------ sending
def send(cfg, stock: str, action: str, percent, reason: str):
    if is_blocked(stock):                           # second safety net
        return
    name = f"{action}max.json" if percent is None else f"{action}percent.json"
    path = Path(cfg["commands_dir"]) / stock / name
    label = f"{action.upper():5} {stock} {'MAX' if percent is None else f'{percent}%'}  - {reason}"
    stamp = time.strftime("%H:%M:%S")
    if cfg["dry_run"]:
        print(f"\n[{stamp}] [DRY RUN] would {label}")
        return
    cur = read_json(path)
    if cur and cur.get("execute"):
        return                                      # previous command not picked up yet
    payload = {"execute": True}
    if percent is not None:
        payload["percent"] = percent
    try:
        path.write_text(json.dumps(payload, indent=2))
        print(f"\n[{stamp}] [SENT] {label}")
    except OSError as e:
        print(f"\n[{stamp}] could not write {path}: {e}")


# --------------------------------------------------------------------- loop
def run_cycle(cfg, state, market, history):
    player = market["player"]
    positions = {p["stockId"]: p for p in player.get("positions", [])}
    prices = {s["stockId"]: [x["price"] for x in s["samples"]] for s in history["stocks"]}
    now_ms = market["serverTimeMs"]
    chosen = set(cfg["stocks"])

    for r in market.get("commandResults", []):
        key = json.dumps(r, sort_keys=True)
        if key not in state["seen"]:
            state["seen"].add(key)
            print(f"\n[game result] {r}")

    for s in market["stocks"]:
        sid = s["stockId"]
        if is_blocked(sid, s.get("name", "")):
            continue
        if not s.get("unlocked") or (chosen and sid not in chosen):
            continue
        if s["price"] < cfg["min_price"] or sid not in prices:
            continue
        z = zscore(prices[sid], cfg)
        if z is None:
            continue
        action = decide(cfg, s["price"], z, positions.get(sid, {}), now_ms,
                        player, num(s.get("availableShares")))
        if action:
            send(cfg, sid, *action)


def start_bot(cfg):
    if not folders_ok(cfg):
        print("\n  Set both folders first (menu option 5).")
        return
    mode = "DRY RUN (nothing is traded)" if cfg["dry_run"] else "LIVE TRADING"
    print(f"\nBot running - {mode}")
    print("Press Ctrl+C to stop and go back to the menu.\n")
    state = {"last_seq": None, "seen": set()}
    try:
        while True:
            market = read_json(Path(cfg["export_dir"]) / "market.json")
            history = read_json(Path(cfg["export_dir"]) / "history.json")
            if not market or not history or not market.get("marketReady"):
                print("\rWaiting for market data...        ", end="", flush=True)
                time.sleep(cfg["poll_seconds"])
                continue
            if market["sequence"] != state["last_seq"]:
                state["last_seq"] = market["sequence"]
                run_cycle(cfg, state, market, history)
                cash = num(market["player"].get("cash"))
                print(f"\r{time.strftime('%H:%M:%S')}  update #{market['sequence']}  "
                      f"cash {cash:,.0f}  [{'DRY' if cfg['dry_run'] else 'LIVE'}]   ",
                      end="", flush=True)
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\n\nBot stopped.")


# -------------------------------------------------------------------- menus
def menu_mode(cfg):
    print("\n--- Mode ---")
    print(f"  Now: {'DRY RUN' if cfg['dry_run'] else 'LIVE TRADING'}")
    print("  1. Dry run (only print what it would do)")
    print("  2. Live trading (really trades)")
    print("  0. Back")
    c = ask_choice("Choose: ", {0, 1, 2})
    if c == 1:
        cfg["dry_run"] = True
    elif c == 2:
        print("\n  LIVE mode will send real trades to your game.")
        print("  1. Yes, switch to LIVE")
        print("  2. No, cancel")
        if ask_choice("Choose: ", {1, 2}) == 1:
            cfg["dry_run"] = False
    save_config(cfg)


def menu_stocks(cfg):
    market = read_json(Path(cfg["export_dir"]) / "market.json") if cfg["export_dir"] else None
    if not market:
        print("\n  Can't read market.json - set the export folder first (option 5).")
        return
    stocks = [(s["stockId"], s.get("name", s["stockId"])) for s in market["stocks"]]
    while True:
        print("\n--- Stocks to trade ---")
        chosen = set(cfg["stocks"])
        print("  (none ticked = trade every allowed stock)")
        for i, (sid, name) in enumerate(stocks, 1):
            if is_blocked(sid, name):
                print(f"  {i}. {name:8} [BLOCKED - never traded]")
            else:
                print(f"  {i}. {name:8} [{'x' if sid in chosen else ' '}]")
        print("  0. Back")
        c = ask_choice("Type a number to tick/untick: ", set(range(len(stocks) + 1)))
        if c == 0:
            break
        sid, name = stocks[c - 1]
        if is_blocked(sid, name):
            print("  That stock is permanently blocked.")
            continue
        if sid in chosen:
            chosen.remove(sid)
        else:
            chosen.add(sid)
        cfg["stocks"] = sorted(chosen)
        save_config(cfg)


STRATEGY_ITEMS = [
    ("entry_z", "Entry strength (z-score to open a trade)", float, 0.5, 6),
    ("exit_z", "Exit tolerance (z-score to close)", float, 0.0, 3),
    ("trade_percent", "Trade size (% per buy/short)", float, 1, 100),
    ("stop_loss", "Stop-loss (% against us)", float, 1, 90),
    ("lookback", "Lookback (samples, ~seconds)", int, 20, 900),
    ("min_price", "Ignore stocks cheaper than", float, 0, 1000),
]


def menu_strategy(cfg):
    while True:
        print("\n--- Strategy settings ---")
        for i, (key, label, *_rest) in enumerate(STRATEGY_ITEMS, 1):
            print(f"  {i}. {label}: {cfg[key]}")
        print("  0. Back")
        c = ask_choice("Pick a setting to change: ", set(range(len(STRATEGY_ITEMS) + 1)))
        if c == 0:
            break
        key, label, cast, lo, hi = STRATEGY_ITEMS[c - 1]
        cfg[key] = ask_number(label, cfg[key], cast, lo, hi)
        cfg["min_samples"] = min(cfg["min_samples"], int(cfg["lookback"]))
        save_config(cfg)


def menu_folders(cfg):
    print("\n--- Folders ---")
    cfg["export_dir"] = ask_folder("Export", cfg["export_dir"])
    cfg["commands_dir"] = ask_folder("Commands", cfg["commands_dir"])
    save_config(cfg)


def show_settings(cfg):
    print("\n--- Current settings ---")
    print(f"  Mode:          {'DRY RUN' if cfg['dry_run'] else 'LIVE TRADING'}")
    print(f"  Export folder: {cfg['export_dir'] or 'not set'}")
    print(f"  Commands:      {cfg['commands_dir'] or 'not set'}")
    print(f"  Stocks:        {', '.join(cfg['stocks']) if cfg['stocks'] else 'all allowed'}")
    print("  Never traded:  $BANK, $BASE")
    for key, label, *_rest in STRATEGY_ITEMS:
        print(f"  {label}: {cfg[key]}")


def main():
    cfg = load_config()
    print("=== Screen Stocks Trading Bot ===")
    while True:
        print(f"\nMode: {'DRY RUN' if cfg['dry_run'] else 'LIVE'}   "
              f"Folders: {'ok' if folders_ok(cfg) else 'NOT SET'}")
        print("  1. Start bot")
        print("  2. Mode (dry run / live)")
        print("  3. Choose stocks")
        print("  4. Strategy settings")
        print("  5. Set folders")
        print("  6. Show all settings")
        print("  0. Quit")
        c = ask_choice("Choose: ", {0, 1, 2, 3, 4, 5, 6})
        if c == 0:
            break
        if c == 1:
            start_bot(cfg)
        elif c == 2:
            menu_mode(cfg)
        elif c == 3:
            menu_stocks(cfg)
        elif c == 4:
            menu_strategy(cfg)
        elif c == 5:
            menu_folders(cfg)
        elif c == 6:
            show_settings(cfg)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nBye.")
