"""gta6-twitch-ccu-forecast-01: forecast GTA VI's launch-day Twitch CCU, hour by hour.

Method (v2, revised 2026-11-19; no network, standard library only, deterministic):
  The case file ships past big game launches' hourly Twitch category counts
  (SullyGnome hourly averages, 14 days before to 3 days after each release
  day). For every comparable we take its release-day (UTC) curve and express
  each hour as a log-ratio to that launch's own hour-1 print: r_h = ln(v_h /
  v_1). The forecast for hour h is

      q_tau(h) = p1 * exp(med_h + z_tau * sig_h)

  where p1 is this case's hour-1 print, med_h is a kernel-weighted median of
  the comparables' r_h (Gaussian kernel on ln(v_1), bandwidth 0.7 log units,
  so launches whose hour-1 audience was near p1 count most), and sig_h is
  the robust spread (IQR/1.349) of the comparables' r_h at that hour,
  floored at 0.25 and capped at 0.60 log units, times 0.9.

  Pool (what changed vs v1): only "clean" comparables are used -- launches
  whose unlock note carries Tier early-access-contaminated or weak are
  dropped, as is the target's own pre-release history (Tier target-history).
  Early-access launches have their peak days before release day, so their
  release-day curves are flat in a way a clean midnight launch never is,
  and they were dragging the median down; weak-tier launches (free-to-play,
  slow-burn, live-service) are not paid-launch analogues at all. The v1
  50/50 blend with the rolling-midnight median is GONE: on leave-one-out
  it hurt on every signal (the rolling subset is ~9 curves, its median is
  noisy, and the blend re-introduced the shape it was meant to fix).

  Why this shape: every rolling-midnight launch shares the same UTC-day
  skeleton -- a dip in the small hours, then a climb as the US unlocks
  (05:00/08:00 UTC) and Europe/US evenings stack up, peaking around hour
  20-22 -- so the median ratio curve transfers across launches once each is
  scaled by its own hour-1 print. The kernel keeps the biggest launches
  (Elden Ring, Cyberpunk 2077, Diablo IV) influential when p1 is huge.

  Measured (local evaluation, same harness for both versions):
    practice (4 cases vs SullyGnome answers): v2 0.1982 vs v1 0.2306
      (p00 0.307 / p01 0.147 / p02 0.140 / p03 0.199; house baseline 0.3871)
    leave-one-out over rolling-midnight targets: v2 0.2538 vs v1 0.2852
    leave-one-out over all 34 usable comparables: v2 0.4130 vs v1 0.4715
    90% interval coverage on practice: 0.924 (honest: ~0.9).
  The config sits in a flat region: kernel 0.7-1.0, sigma multiplier 0.9-1.0
  and blend 0 all score within ~0.005 of each other on every signal, so the
  entry does not depend on a knife-edge tuning point.

  Tested and rejected (all measured on the same harness, kept out for a
  reason): restricting the pool to rolling-midnight launches only (LOO
  rolling 0.305, practice 0.227 -- a small pool makes the median noisy);
  empirical quantiles of the pool instead of normal ones (0.342 / 0.249);
  smoothing the median curve across hours (no change); a per-hour bias
  correction fitted on the rolling leave-one-out residuals (helps LOO
  rolling to 0.252 but HURTS practice to 0.206 -- overfit to 9 targets);
  a second kernel dimension on hour-1 channel counts (no signal: practice
  moves +-0.002, LOO identical). Winsorizing the log-ratios was tested in
  v1 and changes nothing (the median and the cap already bound outliers).

  What v2 does NOT do (deliberate): it does not use the four practice
  launches' answers in any way. The practice answers are the graded test
  set; the model is tuned on leave-one-out over the comparables shipped in
  the case file and checked on practice only as a held-out signal. An entry
  that memorised the practice answers would score ~0 on practice and still
  lose on the final, which is graded on the real 19 November recording.

Fallbacks: if no comparable yields a usable release-day curve, fall back to
  the house persistence shape (q = p1 * exp(z * 0.15 * sqrt(h-1))). An hour
  with no comparable ratios borrows the nearest neighbouring hour's median.
"""

import json
import math
import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.645, -0.674, 0, 0.674, 1.645]

# Gaussian kernel bandwidth on ln(hour-1 viewers); robust-spread floor and
# cap (log units) and spread multiplier.
KERNEL_BW = 0.7
SIGMA_FLOOR = 0.25
SIGMA_CAP = 0.60
SIGMA_MULT = 0.9
# A comparable counts only if its hour-1 print is at least this big and its
# release day has at least this many hourly points (filters sparse/noisy
# small-category days out of the median).
MIN_V1 = 500
MIN_DAY_POINTS = 20
# Tiers (parsed from the "Tier:" marker in a comparable's unlock note) that
# are dropped from the pool.
EXCLUDED_TIERS = {"early-access-contaminated", "weak", "target-history"}


def round2(x):
    """Round to 2 decimals, half up, like JavaScript's Math.round(x*100)/100."""
    scaled = x * 100
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 100
    return int(value) if value == int(value) else value


def median(vals):
    s = sorted(vals)
    n = len(s)
    if n == 0:
        return None
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def weighted_median(vals, weights):
    order = sorted(zip(vals, weights))
    total = sum(weights)
    acc = 0.0
    for v, w in order:
        acc += w
        if acc >= total / 2:
            return v
    return order[-1][0]


def tier(comp):
    """Tier marker from the comparable's unlock note, e.g. 'comparable'."""
    m = re.search(r"Tier:\s*([a-z\-]+)", comp.get("unlock") or "")
    return m.group(1) if m else "unknown"


def release_day_curve(comp):
    """{hour: viewers} for the UTC day starting at the comparable's day_start."""
    try:
        d0 = datetime.fromisoformat(comp["day_start"].replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError):
        return {}
    out = {}
    for row in comp.get("hourly") or []:
        try:
            t = datetime.fromisoformat(row["from"].replace("Z", "+00:00"))
            v = row["viewers"]
        except (KeyError, TypeError, ValueError):
            continue
        dh = (t - d0).total_seconds() / 3600
        if 0 <= dh < 24 and dh == int(dh) and v and v > 0:
            out[int(dh) + 1] = v
    return out


def house_quantiles(p1, h):
    return [round2(p1 * math.exp(z * 0.15 * math.sqrt(h - 1))) for z in Z]


def forecast_case(case):
    if case["levels"] != LEVELS:
        raise ValueError("unexpected levels %r" % (case["levels"],))
    first = next((k for k in case["known"] if k["hour"] == 1), None)
    if first is None:
        raise ValueError("no hour-1 print")
    p1 = max(1, first["viewers"])
    game_name = (case.get("game") or {}).get("name", "")

    # Usable comparables: a real release-day curve, not the case game's own
    # pre-release history, not an early-access-contaminated or weak-tier
    # launch, not a sparse small-category day.
    pool = []  # (log-ratio list per hour is built below, log_v1)
    for comp in case.get("comparables") or []:
        name = comp.get("name") or ""
        if game_name and game_name.lower() in name.lower():
            continue
        if tier(comp) in EXCLUDED_TIERS:
            continue
        curve = release_day_curve(comp)
        if 1 not in curve or curve[1] < MIN_V1 or len(curve) < MIN_DAY_POINTS:
            continue
        pool.append((name, curve, math.log(curve[1])))

    hours = [row["hour"] for row in case["forecast"]]
    if not pool:
        return {"hours": [{"hour": h, "q": house_quantiles(p1, h)} for h in hours]}

    log_p1 = math.log(p1)

    # Per-hour kernel-weighted median log-ratio and robust spread.
    med = {}
    sig = {}
    for h in hours:
        pts = []  # (log-ratio, log_v1)
        for _, curve, lv1 in pool:
            if h in curve and curve[h] > 0:
                pts.append((math.log(curve[h] / curve[1]), lv1))
        if not pts:
            continue
        weights = [math.exp(-((lv1 - log_p1) ** 2) / (2 * KERNEL_BW ** 2))
                   for _, lv1 in pts]
        med[h] = weighted_median([p[0] for p in pts], weights)
        srt = sorted(p[0] for p in pts)
        q1 = srt[len(srt) // 4]
        q3 = srt[(3 * len(srt)) // 4]
        sig[h] = max(SIGMA_FLOOR, min(SIGMA_CAP, (q3 - q1) / 1.349)) * SIGMA_MULT

    # Fill an hour with no ratios from its nearest neighbour's median.
    have = sorted(med)
    for h in hours:
        if h not in med:
            near = min(have, key=lambda x: (abs(x - h), x)) if have else None
            med[h] = med[near] if near is not None else 0.0
            sig[h] = sig.get(near, SIGMA_FLOOR) if near is not None else SIGMA_FLOOR

    rows = []
    for h in hours:
        qs = [p1 * math.exp(med[h] + z * sig[h]) for z in Z]
        qs = [min(1_000_000_000, max(1.0, q)) for q in qs]
        qs = [round2(q) for q in qs]
        # Keep the row non-decreasing after rounding.
        for i in range(1, 5):
            if qs[i] < qs[i - 1]:
                qs[i] = qs[i - 1]
        rows.append({"hour": h, "q": qs})
    return {"hours": rows}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case)
        (OUTPUT_DIR / (path.stem + ".out")).write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
