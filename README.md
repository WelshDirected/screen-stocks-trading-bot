# Screen Stocks Trading Bot

A small Python program that trades in **Screen Stocks** for you using the game's official mod support. It reads your price history, decides when to buy, sell, short or cover, and presses the buttons by editing the game's command files.

It runs in a command-line window and is controlled entirely by typing numbers from menus.

---

## 1. Enable mods in the game

1. Close the game completely.
2. Go to:
   `C:\Users\YOURUSERNAME\AppData\LocalLow\Conradical Games\Screen Stocks`
   (Replace `YOURUSERNAME` with your Windows username. `AppData` is a hidden folder. If you can't see it, paste the path straight into the File Explorer address bar.)
3. Open `thesmallshort_online_settings.sav` in a text editor (Notepad is fine) and change `"modSupport"` to `"true"`.
4. Save the file, then start the game.
5. A new folder called **`mods`** now appears next to the settings file. It contains:
   - **`commands`**: one folder per stock, with the command files used to trade
   - **`export`**: your price history and market data (`history.json` and `market.json`)
   - a folder for your custom skins (not used by this bot)

---

## 2. Install the bot

1. Install **Python 3.10 or newer** from [python.org](https://www.python.org/downloads/). During installation, tick "Add Python to PATH".
2. Put `screen_stocks_bot_cli.py` anywhere you like (for example, your Desktop).
3. No extra libraries are needed.

---

## 3. First-time setup

1. Open a Command Prompt in the folder with the script, and run:
   ```
   python screen_stocks_bot_cli.py
   ```
2. Choose **5. Set folders** and enter the two paths. They are inside the `mods` folder from step 1:
   - Export: `C:\Users\YOURUSERNAME\AppData\LocalLow\Conradical Games\Screen Stocks\mods\export`
   - Commands: `C:\Users\YOURUSERNAME\AppData\LocalLow\Conradical Games\Screen Stocks\mods\commands`
3. Leave the mode on **Dry run** for now.
4. Make sure the game is running, then choose **1. Start bot**.

Your settings are saved in `screen_stocks_bot_config.json` next to the script, so you only need to do this once.

---

## 4. The menu

| Option | What it does |
|---|---|
| **1. Start bot** | Starts watching the market. Press **Ctrl+C** to stop and return to the menu. |
| **2. Mode** | Switch between **Dry run** (only prints what it would do) and **Live** (really trades). Live asks you to confirm. |
| **3. Choose stocks** | Tick or untick which stocks the bot may trade. If none are ticked, it trades every allowed stock. |
| **4. Strategy settings** | Change how cautious or aggressive it is (see below). |
| **5. Set folders** | Set the `export` and `commands` folder paths. |
| **6. Show all settings** | Prints everything currently set. |
| **0. Quit** | Exits. |

While running, you'll see a status line with the time, the update number, your cash and the mode. Every time the bot makes (or would make) a trade, it prints a line such as:

```
[12:04:31] [DRY RUN] would SHORT $QUIK 10%  - expensive (z=2.60)
```

---

## 5. How the strategy works

The bot assumes prices **bounce back toward their recent average**.

- Price **much lower** than the last couple of minutes' average: it **buys**, then **sells** once the price recovers.
- Price **much higher** than average: it **shorts**, then **covers** once the price falls back.

"Much" is measured with a z-score, which is how many standard deviations the price is from its average. A z-score of 2 means unusually far from average.

This is a guess about how the market behaves, not a guarantee. If a stock keeps trending one way instead of bouncing back, the bot will lose money on it.

### Strategy settings (menu option 4)

| Setting | Default | Meaning |
|---|---|---|
| Entry strength | 2.0 | How far from average before it opens a trade. Higher means fewer, pickier trades. |
| Exit tolerance | 0.3 | It closes a trade once the price is within this distance of average. |
| Trade size | 10 | Percent value sent with each buy or short. |
| Stop-loss | 20 | Closes a position if it moves this many percent against you. |
| Lookback | 120 | How many recent price samples (about one per second) make up the average. |
| Ignore stocks cheaper than | 1.0 | Skips very cheap, very noisy stocks. |

---

## 6. Safety

- **Always start in Dry run.** Watch what it says for a while before switching to Live.
- **`$BANK` and `$BASE` are never traded.** This is built into the program and can't be changed from the menus. (The game calls `$BASE` by the internal name `$PLAIN`; both names are blocked.) The bot also ignores any open position you hold in them, so manage those yourself.
- It respects the game's buy and short cooldowns.
- It will not send a new command to a file while the previous one still has `"execute": true`.
- **Start with small trade sizes** and keep an eye on it.

---

## 7. How it works behind the scenes

Every second the bot reads the game's files, and when `market.json` has updated, it works out what to do.

- **Reads:** `mods\export\market.json` (prices, your cash and positions, cooldowns) and `mods\export\history.json` (recent price history).
- **Writes:** `mods\commands\<STOCK>\<action>.json`, for example `buypercent.json` or `closemax.json`.

Each stock folder has these command files:

| Action | All-in version | Percent version |
|---|---|---|
| buy | `buymax.json` | `buypercent.json` |
| sell | `sellmax.json` | `sellpercent.json` |
| short | `shortmax.json` | `shortpercent.json` |
| cover | `covermax.json` | `coverpercent.json` |
| close | `closemax.json` | `closepercent.json` |

To trade, the bot sets `"execute": true` (and `"percent"` for the percent versions). The game then carries out the trade.

---

## 8. Troubleshooting

| Problem | Try this |
|---|---|
| No `mods` folder appeared | Make sure the game was **fully closed** when you edited the `.sav` file, that `modSupport` is `"true"`, and that you've launched the game since. |
| "Folders: NOT SET" in the menu | Use option 5 and enter both folder paths. |
| "Can't read market.json" in the stock list | Check the export folder path, and make sure the game is running. |
| "Waiting for market data..." | The game hasn't written fresh data yet. Make sure it's open and in a market screen. |
| It never trades | That can be normal. It only acts when a price is far from average. Lower **Entry strength** in the settings to make it trade more often. |
| Trades don't happen in Live mode | Check the `commandResults` messages the bot prints (shown as `[game result]`), and whether you are still on a buy or short cooldown. |

---

## 9. Things not yet confirmed

These haven't been tested in the game yet, so try one small manual trade to check:

- Whether the game sets `execute` back to `false` after running a command.
- Whether `percent` on a buy means a percent of your cash, and on a sell means a percent of your position.

---
