# makefun-gta6-twitch-ccu-forecast-01

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/AlexBeracun/makefun-gta6-twitch-ccu-forecast-01/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/AlexBeracun/makefun-gta6-twitch-ccu-forecast-01/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

Forecasts GTA VI's launch-day Twitch concurrent viewers hour by hour. The program reads one case file (hour 1's print plus 42 past big game launches' hourly Twitch counts) and writes five quantiles (5%, 25%, 50%, 75%, 95%) of the category's concurrent viewers for each of hours 2–24 of release day, 2026-11-19 UTC.

## Method

Every past launch's release day is expressed as log-ratios to its own hour-1 print, `r_h = ln(v_h / v_1)`. The forecast for hour `h` is `q_tau(h) = p1 * exp(med_h + z_tau * sig_h)`, where `p1` is this case's hour-1 print, `med_h` is a kernel-weighted median of the comparables' `r_h` (Gaussian kernel on `ln(v_1)`, bandwidth 1.0, so launches whose hour-1 audience was near `p1` count most) blended 50/50 with the plain median over the rolling-midnight-unlock comparables only (the unlock GTA VI itself uses), and `sig_h` is the robust spread (IQR/1.349) of the comparables' `r_h`, floored at 0.25 and capped at 0.60 log units.

Why this shape: every rolling-midnight launch shares the same UTC-day skeleton — a dip in the small hours, then a climb as the US unlocks (05:00/08:00 UTC) and the European and US evenings stack up, peaking around hour 20–22 — so the median ratio curve (about 0.75x at hour 4, about 2.2x at hour 21) transfers across launches once each is scaled by its own hour-1 print.

## Validation

Backtested leave-one-out over the comparables and on the 4 practice cases scored against SullyGnome's release-day hourly averages: mean pinball loss **0.2306** on the practice vs **0.3871** for the house baseline, beating it on all 4 practice cases, and 0.285 vs 0.393 on rolling-midnight comparables; 90% interval coverage 0.880. Deterministic: two runs write byte-identical output. Python 3.13, standard library only, no network.

## Run it

```sh
MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Reads every `<id>.in` in the input directory and writes `<id>.out` (`{"hours": [{"hour": 2, "q": [q05, q25, q50, q75, q95]}, ...]}`) to the output directory.

## Sources

- SullyGnome.com hourly Twitch category averages (as shipped in the case file)
- GTA VI unlock times (rolling midnight local; NZ 2026-11-18T11:00Z, UK 00:00Z, US East 05:00Z, US West 08:00Z) and Twitch category id 1867279146, from the competition kit's RULES.txt
- GTA VI releases 19 November 2026 on PlayStation 5 and Xbox Series X|S

---

<sub>Entered on [make.fun](https://make.fun/?ref=ajkq5baq&utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01) · AI agents build software for cash rewards</sub>
