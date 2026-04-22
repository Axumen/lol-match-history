# Champion Select Metric: Methodology & Calculation Procedure

This document explains how the **champion select metric application** in `champion_select_metric.py` computes pick recommendations.

## 1) Purpose

At champion-select time, the application scores each candidate pick `c` with:

`V(c | S_t) = AllySynergy(c) + EnemyPressure(c) + FutureUncertainty(c)`

and recommends the highest-scoring candidate.

---

## 2) Required Inputs

The scoring function requires three explicit draft inputs:

- `ally_faceup_champions`
- `enemy_faceup_champions`
- `candidate_champions`

It also uses:

- `player_role`
- `player_champion_context` (optional)
- `input_file` (default from config)
- `match_count` (recent-match window)
- `include_future_uncertainty` (toggle)

The engine validates the required draft lists before any computation.

---

## 3) Match Data Extraction

The engine reads rows from `Output.csv`-style data, and for each row builds:

- `game_id`
- `player_win`
- `allies` (5 champions)
- `enemies` (5 champions)

Rows are sorted by `game_id` descending and truncated to the most recent `match_count` matches.

---

## 4) Baseline & Smoothing

A baseline win rate is computed on the selected recent window:

`baseline = total_wins / total_matches`

Pairwise win rates use Bayesian-style smoothing:

`smoothed_rate = (wins + k * baseline) / (wins + losses + k)`

with `k = 8.0`.

This stabilizes sparse matchups and avoids overreacting to tiny samples.

---

## 5) Ally Synergy Term `A(c, a)`

For each visible ally `a`, the app finds matches where **both** `c` and `a` were on the player's team and computes:

1. `p = smoothed_rate(wins, losses, baseline)`
2. `centered = p - 0.5`
3. `magnitude = log(1 + |centered| * 8.0)`
4. `A(c,a) = sign(centered) * magnitude`

Interpretation:

- positive `A(c,a)`: candidate tends to perform better with ally `a`
- negative `A(c,a)`: candidate tends to underperform with ally `a`

---

## 6) Enemy Pressure Term `E(c, e)`

For each visible enemy `e`, the app finds matches where `c` was on allies and `e` was on enemies, then computes:

1. `p = smoothed_rate(wins, losses, baseline)`
2. `centered = p - 0.5`
3. `E(c,e) = sigmoid(6.0 * centered) - 0.5`

Interpretation:

- positive `E(c,e)`: candidate has favorable pressure into enemy `e`
- negative `E(c,e)`: enemy `e` applies pressure versus candidate

The sigmoid keeps this term bounded and robust.

---

## 7) Future Uncertainty Term `U(c)` (optional)

If enabled, the app estimates how unseen champions could impact `c`:

1. Build a `visible` set from current allies, enemies, and candidates.
2. Count all non-visible champions across recent matches.
3. Keep `top_k = 12` most frequent unseen champions.
4. For each unseen `x`, compute interaction via the same enemy-pressure primitive:
   - `interaction(c,x) = E(c,x)`
5. Weight by empirical frequency and normalize:

`U(c) = (sum_x w_x * interaction(c,x)) / (sum_x w_x)`

If no unseen distribution exists, `U(c) = 0`.

---

## 8) Final Candidate Score

For each candidate `c`:

- `ally_sum(c) = sum_{a in ally_faceup} A(c,a)`
- `enemy_sum(c) = sum_{e in enemy_faceup} E(c,e)`
- `uncertainty(c) = U(c)` if enabled else `0`
- `total(c) = ally_sum(c) + enemy_sum(c) + uncertainty(c)`

Candidates are ranked by `total(c)` descending.

Top candidate is returned as the recommendation.

---

## 9) Output Structure

The application returns:

- `recommended_pick`
- `ranking` for all candidates
- per-candidate breakdown:
  - `ally_sum`
  - `enemy_sum`
  - `future_uncertainty`
  - `total`
  - pair-level details for allies and enemies

This makes the recommendation auditable rather than a black-box score.

---

## 10) Practical Notes

- The method is **asymmetric** by design: ally synergy and enemy pressure are separate functions.
- Recent-match slicing by descending `game_id` keeps the metric recency-sensitive.
- Smoothing plus bounded transforms (`log1p`, `sigmoid`) reduces volatility in low-sample situations.
