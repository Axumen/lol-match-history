# Codex Handoff 3: Pool Ban Statistics Across All Matches, But Condition Performance Metrics on the Held Champion

## Goal

Document the modeling choice that:

1. **Ban statistics** should usually be computed across all matches, regardless of which champion the player later ends up playing.
2. **Performance / threat metrics** should be computed only from matches where the player actually played the requested held-constant champion.

This handoff is intended for implementation in Codex-style agent workflows.

---

## Core Idea

Draft bans occur **before** the player's eventual champion pick is known.

Because of that timing:

- the probability that other players ban champion `c`
- and the probability that champion `c` is removed by the other 9 bans

are usually **not conditioned on what champion the player later picks**.

By contrast, matchup performance metrics such as:

- win rate against champion `c`
- win rate with champion `c`
- ally/enemy effect on player results

**must** be conditioned on the player actually playing the requested held champion `h`.

So the system should split into:

- a **champion-agnostic ban-probability component**
- a **champion-specific performance component**

---

## Definitions

Let:

- `h` = the held-constant champion played by the player in the performance model
- `c` = a candidate champion being evaluated for ban priority

For each match, track:

```python
{
  "win": 0 or 1,
  "player_champion_id": str,
  "your_ban_champion_id": str | None,
  "other9_banned_champion_ids": list[str],
  "ally_champion_ids": list[str],
  "enemy_champion_ids": list[str],
}
```

Derived indicators for champion `c`:

```python
player_played_h(m) = 1 if player_champion_id == h else 0
you_ban_m(c)       = 1 if your_ban_champion_id == c else 0
other9_ban_m(c)    = 1 if c in other9_banned_champion_ids else 0
ally_has_m(c)      = 1 if c in ally_champion_ids else 0
enemy_has_m(c)     = 1 if c in enemy_champion_ids else 0
win_m              = 1 if match won else 0
```

---

## Part 1: Ban Statistics Should Ignore the Later Player Pick

### Main quantity
Define:

```python
B_minus_you(c) = P(at least one of the other 9 players bans champion c)
```

Because this event happens before the player’s own eventual champion pick is known, estimate it from **all matches**, not just matches where the player later played champion `h`.

Empirical estimate:

```python
B_minus_you_hat(c) = sum_m other9_ban_m(c) / N
```

or with recency weights `w_m`:

```python
B_minus_you_hat(c) = sum_m w_m * other9_ban_m(c) / sum_m w_m
```

Important:
- This excludes the player's own ban.
- This pools across all matches.
- This is the recommended default when bans occur before the player's champion is known.

---

## Why This Pooling Is Usually Correct

The event:

```python
other 9 players banned champion c
```

is a pre-pick event relative to the player's final champion choice.

So if the player later picks `h`, that later pick usually should not be treated as a causal input to the ban-probability estimate.

Therefore:

- `B_minus_you(c)` should generally be pooled across all matches
- not estimated as `B_minus_you(c | h)` by default

---

## Caveat

If the player's eventual held champion `h` is strongly correlated with particular contexts that also alter ban behavior, then a more refined model may use:

```python
B_minus_you(c | context)
```

or even:

```python
B_minus_you(c | h)
```

But this should be treated as an advanced refinement, not the default.

Recommended default:
- use pooled `B_minus_you(c)` across all matches

---

## Part 2: Performance Metrics Must Condition on the Held Champion

Performance metrics should only use matches where the player actually played the requested champion `h`.

### Enemy-side held-champion win rate

```python
p_E(c | h) = P(win | enemy has c, player played h)
```

Empirical estimate:

```python
p_E_hat(c | h) =
    sum_m win_m * enemy_has_m(c) * player_played_h(m)
    /
    sum_m enemy_has_m(c) * player_played_h(m)
```

### Ally-side held-champion win rate

```python
p_A(c | h) = P(win | ally has c, player played h)
```

Empirical estimate:

```python
p_A_hat(c | h) =
    sum_m win_m * ally_has_m(c) * player_played_h(m)
    /
    sum_m ally_has_m(c) * player_played_h(m)
```

These should not be pooled across the player's other champions if the goal is champion-specific ban advice.

---

## Smoothed Held-Champion Rates

To stabilize sparse data, shrink toward baselines.

Let:

- `baseline_enemy_h` = baseline player win rate when playing `h`
- `baseline_ally_h` = baseline player win rate when playing `h`
- `kE`, `kA` = smoothing constants

Then:

```python
pE_tilde(c | h) =
    (wins_enemy_h(c) + kE * baseline_enemy_h)
    /
    (n_enemy_h(c) + kE)

pA_tilde(c | h) =
    (wins_ally_h(c) + kA * baseline_ally_h)
    /
    (n_ally_h(c) + kA)
```

Where:

```python
wins_enemy_h(c) = sum_m win_m * enemy_has_m(c) * player_played_h(m)
n_enemy_h(c)    = sum_m enemy_has_m(c) * player_played_h(m)

wins_ally_h(c)  = sum_m win_m * ally_has_m(c) * player_played_h(m)
n_ally_h(c)     = sum_m ally_has_m(c) * player_played_h(m)
```

---

## Ally Role-Asymmetry Weight

Some champions are uncommon allies due to role constraints.

Keep an ally confidence / availability weight:

```python
w_A(c | h) = n_ally_h(c) / (n_ally_h(c) + k_role)
```

This reduces the influence of sparse ally data.

---

## Held-Champion Threat Score

Define the held-champion threat score as:

```python
T(c | h) =
    (0.5 - pE_tilde(c | h))
    + alpha * w_A(c | h) * (0.5 - pA_tilde(c | h))
```

Recommended default:
- `alpha = 0.2` to `0.3`

Interpretation:
- first term: how bad champion `c` is when left open as an enemy against player champion `h`
- second term: slight bonus if champion `c` is also weak when allied with `h`

---

## Final Recommended Ban Priority

Combine the pooled ban-probability term with the held-champion performance term:

```python
BanPriority(c | h) = T(c | h) * (1 - B_minus_you_hat(c))
```

Expanded:

```python
BanPriority(c | h) =
    (
        (0.5 - pE_tilde(c | h))
        + alpha * w_A(c | h) * (0.5 - pA_tilde(c | h))
    )
    * (1 - B_minus_you_hat(c))
```

This is the recommended default under the assumption that bans happen before the player's eventual champion is known.

---

## Why This Split Is Correct

This separates two different questions:

### Ban side
"Will someone else remove champion `c` anyway?"

This is a pre-pick draft event and usually should be pooled across all matches.

### Performance side
"How bad is champion `c` for me when I am playing champion `h`?"

This is a post-pick performance question and must be conditioned on the player actually using `h`.

So:

- ban probability should be pooled
- performance impact should be champion-specific

---

## Practical Recommendation

Use:

```python
BanPriority(c | h) =
    T(c | h) * (1 - B_minus_you_hat(c))
```

Where:
- `B_minus_you_hat(c)` is estimated from all matches, excluding the player's own ban
- `T(c | h)` is estimated only from matches where the player played `h`

This is the recommended implementation unless you have evidence that public ban behavior changes materially depending on the player's eventual champion.

---

## Optional Advanced Refinement

If you later find that public ban behavior differs by patch, queue type, role, or champion-selection tendencies, you can refine the pooled ban model into:

```python
B_minus_you(c | patch, queue, role, context)
```

But the default production implementation should still be:

- pooled ban probability
- champion-specific performance

---

## Suggested Python Reference Implementation

```python
def smoothed_rate(wins: float, total: float, baseline: float, k: float) -> float:
    return (wins + k * baseline) / (total + k)


def ally_weight(n_ally: float, k_role: float = 10.0) -> float:
    return n_ally / (n_ally + k_role)


def held_champion_threat_score(
    wins_ally_h: float,
    n_ally_h: float,
    wins_enemy_h: float,
    n_enemy_h: float,
    baseline_ally_h: float,
    baseline_enemy_h: float,
    kA: float = 10.0,
    kE: float = 10.0,
    k_role: float = 10.0,
    alpha: float = 0.25,
) -> float:
    pA = smoothed_rate(wins_ally_h, n_ally_h, baseline_ally_h, kA)
    pE = smoothed_rate(wins_enemy_h, n_enemy_h, baseline_enemy_h, kE)
    wA = ally_weight(n_ally_h, k_role)
    return (0.5 - pE) + alpha * wA * (0.5 - pA)


def ban_priority_for_held_champion(
    wins_ally_h: float,
    n_ally_h: float,
    wins_enemy_h: float,
    n_enemy_h: float,
    baseline_ally_h: float,
    baseline_enemy_h: float,
    b_minus_you: float,
    kA: float = 10.0,
    kE: float = 10.0,
    k_role: float = 10.0,
    alpha: float = 0.25,
) -> float:
    t = held_champion_threat_score(
        wins_ally_h=wins_ally_h,
        n_ally_h=n_ally_h,
        wins_enemy_h=wins_enemy_h,
        n_enemy_h=n_enemy_h,
        baseline_ally_h=baseline_ally_h,
        baseline_enemy_h=baseline_enemy_h,
        kA=kA,
        kE=kE,
        k_role=k_role,
        alpha=alpha,
    )
    return t * (1.0 - b_minus_you)
```

---

## Suggested Aggregation Logic

For each candidate champion `c` and held champion `h`:

### Ban side (pooled across all matches)

```python
b_minus_you(c) = sum_m other9_ban_m(c) / N
```

### Performance side (only matches where player played `h`)

```python
wins_enemy_h(c) = sum_m win_m * enemy_has_m(c) * player_played_h(m)
n_enemy_h(c)    = sum_m enemy_has_m(c) * player_played_h(m)

wins_ally_h(c)  = sum_m win_m * ally_has_m(c) * player_played_h(m)
n_ally_h(c)     = sum_m ally_has_m(c) * player_played_h(m)
```

Then rank champions by descending `BanPriority(c | h)`.

---

## Data Model Summary

Recommended per-match fields:

```python
{
  "match_id": str,
  "win": 0 or 1,
  "player_champion_id": str,
  "your_ban_champion_id": str | None,
  "other9_banned_champion_ids": list[str],
  "ally_champion_ids": list[str],
  "enemy_champion_ids": list[str],
}
```

Optional refinement fields:
- patch version
- queue type
- role
- side / draft position
- champion select context features

---

## Plain-Language Summary

Because the player’s final champion is chosen after bans, ban probabilities should usually be estimated across all matches.

But matchup and performance effects should only be estimated from matches where the player actually used the requested champion.

So the recommended structure is:

- pooled ban-probability estimate
- champion-specific performance estimate
- multiply them together for final ban priority

---

## Current OpenAI/Codex Context

OpenAI currently describes Codex as an AI coding agent for software development, available via the Codex app, CLI, IDE integrations, and agent workflows. Structured implementation handoffs like this are suitable inputs for Codex-style coding tasks.
