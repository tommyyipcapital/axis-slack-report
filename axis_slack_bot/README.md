# Axis sUSDx Slack Fair Value Bot

This small bot reads the sUSDx balance for your wallet on Plasma and posts a daily fair-value estimate to Slack.

Current configured position:

- Token: `0x13a099765b34b3aafedb8698cf7fd418e7730012`
- Wallet: `0x332bc14667a9d6d27f816b75a018ba1acc242bd2`
- Live rate contract: `0x24891f7852021413d4acb0641994d045eeadc9be`
- Live rate function: `getRate()`
- USDx/USDT assumption: `1 USDx = 1 USDT`

## Test It Manually

Open Terminal, then run:

```bash
cd /Users/admin/Documents/rong/axis_slack_bot
python3 axis_fair_value_bot.py --dry-run
```

Expected result today is close to:

```text
Balance: 994,886.300076 sUSDx
Live rate: 1 sUSDx = 1.005177620496321032 USDx
Value (USDT): $1,000,037.44
Initial balance (USDT): $1,000,000.00
Net change: +$37.44
Days staked: 0
Projected APY: N/A (day 0)
```

## Send To Slack

1. In Slack, create an incoming webhook for the channel that should receive the daily report.
2. Copy `.env.example` to `.env`.
3. Replace `SLACK_WEBHOOK_URL` with the webhook URL from Slack.
4. Run this from Terminal:

```bash
cd /Users/admin/Documents/rong/axis_slack_bot
set -a
source .env
set +a
python3 axis_fair_value_bot.py
```

## Run Every Day On This Mac

After the manual Slack test works, add a daily cron job:

```bash
crontab -e
```

Paste this line to run every day at 9:00 AM:

```cron
0 9 * * * cd /Users/admin/Documents/rong/axis_slack_bot && set -a && . ./.env && set +a && /usr/bin/python3 axis_fair_value_bot.py
```

## Rate Note

The bot reads the live sUSDx/USDx rate from `getRate()` on the rate contract. It still treats USDx/USDT as `1:1`; change `USDX_USD` only if you want to mark USDx below or above par.

## Run Daily With GitHub Actions

GitHub Actions is better than Mac cron because it runs in the cloud even when your MacBook is off.

The workflow file is:

```text
/Users/admin/Documents/rong/.github/workflows/axis-daily-report.yml
```

It runs every day at `04:00 UTC`, which is `12:00 noon Hong Kong time`.

After this folder is pushed to GitHub:

1. Open the GitHub repository in your browser.
2. Go to `Settings`.
3. Go to `Secrets and variables`.
4. Click `Actions`.
5. Click `New repository secret`.
6. Name it:

```text
SLACK_WEBHOOK_URL
```

7. Paste your Slack webhook URL as the value.
8. Save it.
9. Go to the `Actions` tab.
10. Open `Axis Daily Slack Report`.
11. Click `Run workflow` to test one manual Slack post.
