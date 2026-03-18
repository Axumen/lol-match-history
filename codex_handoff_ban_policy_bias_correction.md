# Codex Handoff 2: Correcting Ban-Policy Feedback Bias by Tracking the Player's Own Ban

## Goal

Extend the previous ban-priority system so it remains valid after deployment, when the player starts repeatedly banning the current top recommendation.

This document explains:

1. Why repeated use of the ban policy creates feedback bias.
2. Why tracking the player's own ban is necessary.
3. What corrected formulas to use after logging the player's own ban.
4. A practical implementation strategy for online updating.

---

## Problem: Policy-Induced Bias

Once the player starts following the current metric, future data is no longer purely observational.

If the player often bans champion `c`, then:

- `c` appears less often in future drafts
- fewer future matches contain `c` as an enemy or ally
- observed matchup statistics for `c` become censored by the player's own policy
- naive re-estimation can make the metric self-reinforcing or stale

This is a classic feedback-loop / intervention bias problem.

---

## Key Principle

Tracking the player's own ban is **necessary but not sufficient**.

It only remedies the bias if the estimator explicitly uses the player's own-ban indicator to separate:

- what **you** removed from the draft
- what the **other 9 players** removed from the draft
- what remained open and therefore could still appear

---

## New Per-Match Logged Fields

For each match `m`, store at minimum:

```python
{
  "match_id": str,
  "win": 0 or 1,

  # Player action
  "your_ban_champion_id": str | None,

  # Other-9 ban set (exclude your own slot)
  "other9_banned_champion_ids": list[str],

  # Actual picks / appearance indicators
  "enemy_champion_ids": list[str],
  "ally_champion_ids": list[str],
}
```

Derived per champion `c`:

```python
you_ban_m(c)       = 1 if your_ban_champion_id == c else 0
other9_ban_m(c)    = 1 if c in other9_banned_champion_ids else 0
enemy_has_m(c)     = 1 if c in enemy_champion_ids else 0
ally_has_m(c)      = 1 if c in ally_champion_ids else 0
win_m              = 1 if match won else 0
```

---

## What to Correct

There are two distinct objects that must be estimated separately.

### 1. Marginal availability if you do not ban champion `c`
This is:

```python
1 - B_minus_you(c)
```

where:

```python
B_minus_you(c) = P(other 9 players ban champion c)
```

This must exclude your own ban completely.

### 2. Open-match threat of champion `c`
This should be estimated only from matches where **you did not ban `c`**, because those are the matches where the champion was not removed by your own intervention.

---

## Corrected Ban-Probability Estimate

For each champion `c`, define:

```python
B_minus_you(c) = P(at least one of the other 9 players bans c)
```

Empirical estimate:

```python
B_minus_you_hat(c) = sum_m other9_ban_m(c) / N
```

or with recency weights `w_m`:

```python
B_minus_you_hat(c) = sum_m w_m * other9_ban_m(c) / sum_m w_m
```

Important:
- This uses all matches.
- Your own ban is not part of this probability.
- This avoids contaminating the "someone else would ban it anyway" term.

---

## Corrected Enemy-Side Win Rate

Naive enemy win rate:

```python
p_E(c) = P(win | enemy has c)
```

Corrected version after tracking your own ban:

```python
p_E_star(c) = P(win | enemy has c, you did not ban c)
```

Empirical estimate:

```python
p_E_star_hat(c) =
    sum_m win_m * enemy_has_m(c) * (1 - you_ban_m(c))
    /
    sum_m enemy_has_m(c) * (1 - you_ban_m(c))
```

This uses only matches where `c` was not your ban.

---

## Corrected Ally-Side Win Rate

Naive ally win rate:

```python
p_A(c) = P(win | ally has c)
```

Corrected version:

```python
p_A_star(c) = P(win | ally has c, you did not ban c)
```

Empirical estimate:

```python
p_A_star_hat(c) =
    sum_m win_m * ally_has_m(c) * (1 - you_ban_m(c))
    /
    sum_m ally_has_m(c) * (1 - you_ban_m(c))
```

---

## Smoothed Corrected Rates

To stabilize estimates, shrink toward baselines.

Let:
- `baseline_enemy`
- `baseline_ally`
- `kE`, `kA` = smoothing constants

Then:

```python
pE_tilde_star(c) =
    (wins_enemy_open(c) + kE * baseline_enemy)
    /
    (n_enemy_open(c) + kE)

pA_tilde_star(c) =
    (wins_ally_open(c) + kA * baseline_ally)
    /
    (n_ally_open(c) + kA)
```

Where:

```python
wins_enemy_open(c) = sum_m win_m * enemy_has_m(c) * (1 - you_ban_m(c))
n_enemy_open(c)    = sum_m enemy_has_m(c) * (1 - you_ban_m(c))

wins_ally_open(c)  = sum_m win_m * ally_has_m(c) * (1 - you_ban_m(c))
n_ally_open(c)     = sum_m ally_has_m(c) * (1 - you_ban_m(c))
```

---

## Ally Role-Asymmetry Weight

Keep the ally-side confidence / availability weight:

```python
w_A(c) = n_ally_open(c) / (n_ally_open(c) + k_role)
```

This makes the ally term weak when ally-side data is sparse or role-constrained.

---

## Corrected Threat Score

Use the corrected open-match rates:

```python
T_star(c) =
    (0.5 - pE_tilde_star(c))
    + alpha * w_A(c) * (0.5 - pA_tilde_star(c))
```

Recommended default:
- `alpha = 0.2` to `0.3`

Interpretation:
- first term: how bad the champion is when left open as an enemy
- second term: slight bonus to banning champions that also underperform as allies

---

## Corrected Ban Priority

Final corrected score:

```python
BanPriority_star(c) = T_star(c) * (1 - B_minus_you_hat(c))
```

Expanded:

```python
BanPriority_star(c) =
    (
        (0.5 - pE_tilde_star(c))
        + alpha * w_A(c) * (0.5 - pA_tilde_star(c))
    )
    * (1 - B_minus_you_hat(c))
```

This is the recommended corrected deployment metric.

---

## Why This Works

This fixes two different biases:

### Bias 1: Public-ban contamination
If your own ban is included in ban-rate estimation, champions you frequently ban look artificially likely to be removed anyway.

Fix:
- estimate `B_minus_you(c)` from the **other 9 players only**

### Bias 2: Threat censorship
If you frequently ban champion `c`, then future observed open-match outcomes for `c` become sparse and nonrepresentative.

Fix:
- estimate matchup rates only from matches where **you did not ban `c`**

---

## Important Limitation

Conditioning on `you did not ban c` is a major improvement, but not fully unbiased if your policy is deterministic or context-dependent.

Why:
- you may choose not to ban `c` only in unusual contexts
- therefore the retained matches may still be selected, not random

To reduce this further, use exploration or propensity weighting.

---

## Better Statistical Fix: Propensity Weighting

If your ban policy is stochastic and logged, let:

```python
pi_m(c) = P(you ban champion c in context x_m)
```

For matches where you did **not** ban `c`, use inverse propensity weighting:

```python
weight_m(c) = 1 / (1 - pi_m(c))
```

Then estimate corrected enemy win rate as:

```python
p_E_IPS_hat(c) =
    sum_m weight_m(c) * win_m * enemy_has_m(c) * (1 - you_ban_m(c))
    /
    sum_m weight_m(c) * enemy_has_m(c) * (1 - you_ban_m(c))
```

Similarly for ally-side:

```python
p_A_IPS_hat(c) =
    sum_m weight_m(c) * win_m * ally_has_m(c) * (1 - you_ban_m(c))
    /
    sum_m weight_m(c) * ally_has_m(c) * (1 - you_ban_m(c))
```

Then replace `pE_tilde_star` and `pA_tilde_star` with smoothed versions of these weighted estimates.

This is the best statistical version if the production policy includes logged stochasticity.

---

## Practical Recommendation

### Minimum version
Use this if you want the simplest deployable correction:

```python
BanPriority_star(c) =
    (
        (0.5 - pE_tilde_star(c))
        + alpha * w_A(c) * (0.5 - pA_tilde_star(c))
    )
    * (1 - B_minus_you_hat(c))
```

Where:
- all ban-probability estimates exclude your own ban
- all threat estimates use only matches where you did not ban `c`

### Better version
Use this if you can support exploration and logged policy probabilities:
- stochastic ban policy over top-k candidates
- log `pi_m(c)`
- apply inverse propensity weighting

---

## Recommended Online Policy

Avoid always banning the single top-ranked champion deterministically.

Instead:
- compute scores for top-k candidates
- sample among them with a softmax or capped stochastic policy
- log the chosen action and policy probability

Example:

```python
P(you ban c | top_k) = exp(lambda * score(c)) / sum_j exp(lambda * score(j))
```

This helps preserve learning and supports causal correction later.

---

## Suggested Python Reference Implementation

```python
def smoothed_rate(wins: float, total: float, baseline: float, k: float) -> float:
    return (wins + k * baseline) / (total + k)


def ally_weight(n_ally_open: float, k_role: float = 10.0) -> float:
    return n_ally_open / (n_ally_open + k_role)


def corrected_threat_score(
    wins_ally_open: float,
    n_ally_open: float,
    wins_enemy_open: float,
    n_enemy_open: float,
    baseline_ally: float,
    baseline_enemy: float,
    kA: float = 10.0,
    kE: float = 10.0,
    k_role: float = 10.0,
    alpha: float = 0.25,
) -> float:
    pA = smoothed_rate(wins_ally_open, n_ally_open, baseline_ally, kA)
    pE = smoothed_rate(wins_enemy_open, n_enemy_open, baseline_enemy, kE)
    wA = ally_weight(n_ally_open, k_role)
    return (0.5 - pE) + alpha * wA * (0.5 - pA)


def corrected_ban_priority(
    wins_ally_open: float,
    n_ally_open: float,
    wins_enemy_open: float,
    n_enemy_open: float,
    baseline_ally: float,
    baseline_enemy: float,
    b_minus_you: float,
    kA: float = 10.0,
    kE: float = 10.0,
    k_role: float = 10.0,
    alpha: float = 0.25,
) -> float:
    t = corrected_threat_score(
        wins_ally_open=wins_ally_open,
        n_ally_open=n_ally_open,
        wins_enemy_open=wins_enemy_open,
        n_enemy_open=n_enemy_open,
        baseline_ally=baseline_ally,
        baseline_enemy=baseline_enemy,
        kA=kA,
        kE=kE,
        k_role=k_role,
        alpha=alpha,
    )
    return t * (1.0 - b_minus_you)
```

---

## Suggested Aggregation Logic

For each champion `c`, compute from logged matches:

```python
wins_enemy_open(c) = sum_m win_m * enemy_has_m(c) * (1 - you_ban_m(c))
n_enemy_open(c)    = sum_m enemy_has_m(c) * (1 - you_ban_m(c))

wins_ally_open(c)  = sum_m win_m * ally_has_m(c) * (1 - you_ban_m(c))
n_ally_open(c)     = sum_m ally_has_m(c) * (1 - you_ban_m(c))

b_minus_you(c)     = sum_m other9_ban_m(c) / N
```

Then rank by `corrected_ban_priority(c)` descending.

---

## Data Model Additions

Add at least the following fields to your draft/match table:

```python
{
  "your_ban_champion_id": str | None,
  "other9_banned_champion_ids": list[str],
  "policy_probability_by_champion": dict[str, float] | None,
}
```

If storage is constrained, it is sufficient to store:
- chosen ban
- candidate set
- chosen-ban probability
- whether each champion of interest was banned by other 9

---

## Plain-Language Summary

Once the player starts using the metric, the data becomes affected by that policy.

The fix is:
1. log the player's own ban,
2. estimate other-9 ban probability separately,
3. estimate matchup threat only from matches where the player did not ban that champion,
4. optionally add stochastic exploration and propensity weighting.

This produces a corrected ban-priority metric that is much less distorted by the player's own repeated bans.

---

## Current OpenAI/Codex Context

OpenAI currently describes Codex as an AI coding agent and provides Codex workflows for implementation-oriented tasks, which is a good fit for a handoff like this. \uE808cite\uE202turn171369search0\uE202turn171369search1\uE202turn171369search2\uE801
