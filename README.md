# Ban Priority Method (Quick Guide)

This project scores which champions are best to ban for a **specific player champion** using two ideas:

1. **Performance threat** (how bad a champion is for your win chance).
2. **Marginal ban value** (how much your ban still matters after accounting for likely bans by others).

---

## 1) Data used from `Output.csv`

Per match row:
- Player outcome (`win`/`loss`)
- Team champions (5 ally + 5 enemy)
- 10 bans
- Optional `player_ban` (last column)

Analysis window:
- Take the **last N matches by highest `gameId`**.
- Keep only matches where the player used the requested champion for performance stats.
- Use all matches in the N-window for ban-behavior stats.

---

## 2) Performance model (requested champion only)

For each champion `c`:
- `W_A, L_A`: wins/losses with `c` as ally
- `W_E, L_E`: wins/losses against `c` as enemy

Smoothed rates:

- `pA~ = (W_A + kA*b) / (n_A + kA)`
- `pE~ = (W_E + kE*b) / (n_E + kE)`

where `b` is baseline win rate in selected matches.

Ally confidence weight:

- `wA = n_A / (n_A + k_role)`

Threat score:

- `Threat(c) = (0.5 - pE~) + alpha * wA * (0.5 - pA~)`

Higher threat means champion `c` tends to be worse if left open.

---

## 3) Ban behavior model (recent N matches)

Estimate probability champion `c` is banned by others:

- `b_minus_you(c) = banned_by_other9_count / N`

Bias handling with `player_ban`:
- If `player_ban` is blank: use all 10 bans.
- If `player_ban` is set: remove one instance of that champion from the row before counting.
- If `player_ban` is `No Ban`: keep all non-`No Ban` bans.

Final priority:

- `BanPriority(c) = Threat(c) * (1 - b_minus_you(c))`

So a champion ranks high when it is both threatening **and** not already likely to be banned by others.

---

## 4) Output columns (main)

In `BanPriorityOutput.csv`, key columns are:
- `threat`
- `b_minus_you`
- `ban_priority`

Extra diagnostics:
- `b_minus_you_when_held`
- `b_minus_you_when_not_held`
- `ban_behavior_lift_vs_not_held`

---

## 5) How to interpret results

Use top `ban_priority` rows first.

- **High threat + low `b_minus_you`**: best bans (your ban has strong marginal value).
- **High threat + high `b_minus_you`**: strong champ, but often banned anyway.
- **Low/negative threat**: usually low-priority bans for this player/champion context.

Practical tip: trust rankings more when `n_enemy` and `n_ally` are reasonably large.
