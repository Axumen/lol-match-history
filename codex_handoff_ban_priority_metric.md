# Codex Handoff: Champion Ban Priority Metric with Unique Team Bans and No-Ban Support

## Goal

Design a player-specific **ban priority** metric for a fixed player/champion context.

The metric should rank champions by the **marginal value of banning them** for this player, taking into account:

1. The champion may be **strong against the player**.
2. The champion may be **weak when allied with the player**.
3. Ally occurrence may be asymmetric or rare because of role constraints.
4. Draft bans are **blind**.
5. Within each team, champion bans are **unique**.
6. Any number of players may choose **No Ban**.
7. The player's own ban should be discounted if the other 9 players are likely to ban that same champion anyway.

---

## Core Inputs Per Champion `c`

### Match outcome counts
- `W_A(c)`: wins with champion `c` as ally
- `L_A(c)`: losses with champion `c` as ally
- `W_E(c)`: wins against champion `c` as enemy
- `L_E(c)`: losses against champion `c` as enemy

### Sample sizes
- `n_A(c) = W_A(c) + L_A(c)`
- `n_E(c) = W_E(c) + L_E(c)`

### Raw win rates
- `p_A(c) = W_A(c) / n_A(c)` if `n_A(c) > 0`
- `p_E(c) = W_E(c) / n_E(c)` if `n_E(c) > 0`

Interpretation:
- `p_A(c)` = player win rate when allied with `c`
- `p_E(c)` = player win rate when facing `c`

---

## Recommended Smoothed Win Rates

To reduce noise, shrink each rate toward a baseline.

Let:
- `b_A` = player's baseline ally-side win rate
- `b_E` = player's baseline enemy-side win rate
- `kA`, `kE` = smoothing constants (example: 10 to 30)

Then:

```python
pA_tilde(c) = (W_A(c) + kA * b_A) / (n_A(c) + kA)    if n_A(c) + kA > 0
pE_tilde(c) = (W_E(c) + kE * b_E) / (n_E(c) + kE)    if n_E(c) + kE > 0
```

---

## Role-Asymmetry Weight for Ally Component

Some champions rarely or never appear as allies in relevant roles.

Use an ally-confidence / availability weight:

```python
w_A(c) = n_A(c) / (n_A(c) + k_role)
```

where `k_role` is a small positive constant such as `10`.

Properties:
- If ally data is sparse, `w_A(c)` is small.
- If ally data is plentiful, `w_A(c)` approaches `1`.

---

## Threat Score Before Ban-Probability Adjustment

For bans, the main concern is whether the champion is **bad when left open**.

Define:

```python
T(c) = (0.5 - pE_tilde(c)) + alpha * w_A(c) * (0.5 - pA_tilde(c))
```

Recommended default:
- `alpha = 0.2` to `0.3`

Interpretation:
- First term: champion is strong against the player if player win rate versus it is below 50%.
- Second term: champion is also a better ban if it is weak when allied with the player, but this should count less than the enemy-threat term.

Higher `T(c)` means the champion is worse for the player if left open.

---

## Exact Marginal Ban Value Under Draft Rules

### Draft assumptions
- Player is considering banning champion `c`.
- There are **4 other bans on player's team**.
- There are **5 bans on enemy team**.
- Within each team, champion bans are **unique**.
- Multiple players may choose **No Ban**.
- Cross-team duplicate bans are allowed.
- Player's own ban matters only if none of the other 9 players bans `c`.

### Exact team-level probabilities
Let:

- `B_A_4(c)` = probability that at least one of the player's other 4 teammates bans `c`
- `B_E_5(c)` = probability that at least one of the 5 enemy players bans `c`

Then the exact marginal value multiplier is:

```python
R(c) = (1 - B_A_4(c)) * (1 - B_E_5(c))
```

And the exact ban-priority metric is:

```python
M(c) = T(c) * R(c)
```

Expanded:

```python
M(c) = T(c) * (1 - B_A_4(c)) * (1 - B_E_5(c))
```

This is exact under the stated rules, assuming the two teams' ban processes are independent.

---

## Equivalent Other-9-Baners Form

Define:

- `B_minus_you(c)` = probability that champion `c` is banned by at least one of the **other 9 players**

Then:

```python
M(c) = T(c) * (1 - B_minus_you(c))
```

This is equivalent to the team-factorized version if:

```python
B_minus_you(c) = B_A_4(c) + B_E_5(c) - B_A_4(c) * B_E_5(c)
```

---

## Important Clarification About No Ban

No Ban does **not** require a separate correction term.

Reason:
- No Ban only changes the probability values `B_A_4(c)` and `B_E_5(c)`.
- The structural formula remains the same because the event "team bans champion c" is still a yes/no event, and champion bans remain unique within the team.

---

## Recommended Final Metric

Use:

```python
BanPriority(c) = (
    (0.5 - pE_tilde(c))
    + alpha * w_A(c) * (0.5 - pA_tilde(c))
) * (1 - B_minus_you(c))
```

or, if team-side probabilities are available:

```python
BanPriority(c) = (
    (0.5 - pE_tilde(c))
    + alpha * w_A(c) * (0.5 - pA_tilde(c))
) * (1 - B_A_4(c)) * (1 - B_E_5(c))
```

Recommended defaults:
- `alpha = 0.25`
- `kA = 10`
- `kE = 10`
- `k_role = 10`

---

## Interpretation

A champion gets a high ban-priority score when:

1. The player tends to lose against it.
2. It is not especially valuable to keep available as an ally.
3. It is not already likely to be banned by the other 9 players.

This makes the metric **marginal**, not just threat-based.

---

## Implementation Notes

### Edge cases
1. If `n_E(c) = 0`, enemy threat is unknown.
   - Use smoothing only, or optionally exclude from rankings until minimum sample.
2. If `n_A(c) = 0`, then:
   - `w_A(c)` will be near `0`
   - ally term contributes little or nothing
3. If `B_minus_you(c)` is unavailable:
   - approximate it from historical draft data
   - or temporarily omit the marginal-ban adjustment

### Minimum sample recommendation
Consider requiring:
- `n_E(c) >= min_enemy_games`
before trusting the ranking strongly.

### Sorting
Sort champions by descending `BanPriority(c)`.

---

## Suggested Python Reference Implementation

```python
def smoothed_rate(wins: int, losses: int, baseline: float, k: float) -> float:
    n = wins + losses
    return (wins + k * baseline) / (n + k)


def ally_weight(n_ally: int, k_role: float = 10.0) -> float:
    return n_ally / (n_ally + k_role)


def threat_score(
    wins_ally: int,
    losses_ally: int,
    wins_enemy: int,
    losses_enemy: int,
    baseline_ally: float,
    baseline_enemy: float,
    kA: float = 10.0,
    kE: float = 10.0,
    k_role: float = 10.0,
    alpha: float = 0.25,
) -> float:
    n_ally = wins_ally + losses_ally

    pA = smoothed_rate(wins_ally, losses_ally, baseline_ally, kA)
    pE = smoothed_rate(wins_enemy, losses_enemy, baseline_enemy, kE)
    wA = ally_weight(n_ally, k_role)

    return (0.5 - pE) + alpha * wA * (0.5 - pA)


def ban_priority_from_other9(
    wins_ally: int,
    losses_ally: int,
    wins_enemy: int,
    losses_enemy: int,
    baseline_ally: float,
    baseline_enemy: float,
    b_minus_you: float,
    kA: float = 10.0,
    kE: float = 10.0,
    k_role: float = 10.0,
    alpha: float = 0.25,
) -> float:
    t = threat_score(
        wins_ally=wins_ally,
        losses_ally=losses_ally,
        wins_enemy=wins_enemy,
        losses_enemy=losses_enemy,
        baseline_ally=baseline_ally,
        baseline_enemy=baseline_enemy,
        kA=kA,
        kE=kE,
        k_role=k_role,
        alpha=alpha,
    )
    return t * (1.0 - b_minus_you)


def ban_priority_from_team_probs(
    wins_ally: int,
    losses_ally: int,
    wins_enemy: int,
    losses_enemy: int,
    baseline_ally: float,
    baseline_enemy: float,
    b_a_4: float,
    b_e_5: float,
    kA: float = 10.0,
    kE: float = 10.0,
    k_role: float = 10.0,
    alpha: float = 0.25,
) -> float:
    t = threat_score(
        wins_ally=wins_ally,
        losses_ally=losses_ally,
        wins_enemy=wins_enemy,
        losses_enemy=losses_enemy,
        baseline_ally=baseline_ally,
        baseline_enemy=baseline_enemy,
        kA=kA,
        kE=kE,
        k_role=k_role,
        alpha=alpha,
    )
    return t * (1.0 - b_a_4) * (1.0 - b_e_5)
```

---

## Suggested Data Model

Per champion, store at least:

```python
{
  "champion_id": str,
  "wins_ally": int,
  "losses_ally": int,
  "wins_enemy": int,
  "losses_enemy": int,
  "b_minus_you": float | None,
  "b_a_4": float | None,
  "b_e_5": float | None,
}
```

Global player-level config:

```python
{
  "baseline_ally": float,
  "baseline_enemy": float,
  "kA": float,
  "kE": float,
  "k_role": float,
  "alpha": float,
}
```

---

## Plain-Language Summary

Use a score that measures:

- how badly a champion performs against the player,
- slightly adjusted by whether the champion is also bad as an ally,
- then multiply by the chance that the champion would still remain unbanned if the player did not ban it.

This produces a **marginal ban value** rather than a naive threat ranking.

---

## Current OpenAI/Codex Terminology

OpenAI currently describes Codex as an AI coding agent and provides a Codex app / CLI / related agent workflows. A structured implementation handoff like this is aligned with current Codex usage and prompting guidance. citeturn700611search0turn700611search1turn700611search14
