import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List

INPUT_FILE = Path("Output.csv")
OUTPUT_FILE = Path("BanPriorityOutput.csv")

# Smoothing defaults from codex_handoff_ban_priority_metric.md
ALPHA = 0.25
K_ALLY = 10.0
K_ENEMY = 10.0
K_ROLE = 10.0


@dataclass
class ChampionCounters:
    wins_ally: int = 0
    losses_ally: int = 0
    wins_enemy: int = 0
    losses_enemy: int = 0
    banned_any: int = 0
    banned_when_held: int = 0
    banned_when_not_held: int = 0


@dataclass
class MatchRow:
    game_version: str
    game_id: str
    player_win: bool
    player_index: int
    player_champion: str
    allies: List[str]
    enemies: List[str]
    bans: List[str]
    player_ban: str


# Expected row layout from GetMatch.py:
# 5 metadata + 10 champions (allies then enemies) + 10 bans [+ optional player_ban]
MIN_COLUMNS = 25


def _smoothed_rate(wins: int, losses: int, baseline: float, k: float) -> float:
    n = wins + losses
    return (wins + k * baseline) / (n + k)


def _ally_weight(n_ally: int, k_role: float = K_ROLE) -> float:
    return n_ally / (n_ally + k_role)


def _read_matches(path: Path) -> List[MatchRow]:
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    matches: List[MatchRow] = []

    with path.open("r", newline="") as f:
        reader = csv.reader(f)
        for row_number, row in enumerate(reader, start=1):
            if not row:
                continue
            if len(row) < MIN_COLUMNS:
                raise ValueError(
                    f"Row {row_number} has {len(row)} columns; expected at least {MIN_COLUMNS}."
                )

            player_index = int(row[3])
            champions = row[5:15]
            bans = row[15:25]
            player_ban = row[25].strip() if len(row) >= 26 else ""

            matches.append(
                MatchRow(
                    game_version=row[0],
                    game_id=row[1],
                    player_win=row[2].strip().lower() == "true",
                    player_index=player_index,
                    player_champion=row[4],
                    allies=champions[:5],
                    enemies=champions[5:],
                    bans=bans,
                    player_ban=player_ban,
                )
            )

    return matches


def _select_recent_window(matches: List[MatchRow], max_matches: int) -> List[MatchRow]:
    if max_matches <= 0:
        return []

    sorted_matches = sorted(matches, key=lambda m: _game_id_sort_key(m.game_id), reverse=True)
    return sorted_matches[:max_matches]


def _game_id_sort_key(game_id: str):
    game_id_str = str(game_id).strip()
    try:
        return int(game_id_str)
    except ValueError:
        return game_id_str


def _filter_matches_by_champion(
    matches: Iterable[MatchRow], player_champion: str
) -> List[MatchRow]:
    champion_key = player_champion.strip().lower()
    return [m for m in matches if m.player_champion.strip().lower() == champion_key]


def _compute_ban_priority_rows(
    champion_matches: Iterable[MatchRow], ban_matches: Iterable[MatchRow]
) -> List[Dict[str, float]]:
    selected = list(champion_matches)
    ban_reference = list(ban_matches)
    total_matches = len(selected)
    ban_reference_matches = len(ban_reference)
    not_held_matches = max(ban_reference_matches - total_matches, 0)

    if total_matches == 0:
        return []

    counters: Dict[str, ChampionCounters] = defaultdict(ChampionCounters)
    total_wins = 0

    for match in selected:
        if match.player_win:
            total_wins += 1

        for champ in match.allies:
            if champ == match.player_champion:
                continue
            if match.player_win:
                counters[champ].wins_ally += 1
            else:
                counters[champ].losses_ally += 1

        for champ in match.enemies:
            if match.player_win:
                counters[champ].wins_enemy += 1
            else:
                counters[champ].losses_enemy += 1

    selected_game_ids = {match.game_id for match in selected}

    for match in ban_reference:
        unique_bans = _other_9_unique_bans(match)
        for banned_champ in unique_bans:
            counters[banned_champ].banned_any += 1
            if match.game_id in selected_game_ids:
                counters[banned_champ].banned_when_held += 1
            else:
                counters[banned_champ].banned_when_not_held += 1

    baseline = total_wins / total_matches

    rows = []
    for champ, c in counters.items():
        n_ally = c.wins_ally + c.losses_ally
        n_enemy = c.wins_enemy + c.losses_enemy

        pA_tilde = _smoothed_rate(c.wins_ally, c.losses_ally, baseline, K_ALLY)
        pE_tilde = _smoothed_rate(c.wins_enemy, c.losses_enemy, baseline, K_ENEMY)
        wA = _ally_weight(n_ally)

        threat = (0.5 - pE_tilde) + ALPHA * wA * (0.5 - pA_tilde)

        # Approximation from Output.csv: we do not know which exact ban is "your" ban,
        # so estimate with probability that champ is banned by any ban slot in the
        # recent-match window (ban behavior does not depend on chosen champion).
        b_minus_you = c.banned_any / ban_reference_matches if ban_reference_matches else 0.0
        b_minus_you_when_held = c.banned_when_held / total_matches if total_matches else 0.0
        b_minus_you_when_not_held = (
            c.banned_when_not_held / not_held_matches if not_held_matches else 0.0
        )
        ban_behavior_lift_vs_not_held = b_minus_you_when_held - b_minus_you_when_not_held
        ban_priority = threat * (1.0 - b_minus_you)

        rows.append(
            {
                "champion": champ,
                "matches_analyzed": total_matches,
                "n_ally": n_ally,
                "n_enemy": n_enemy,
                "wins_ally": c.wins_ally,
                "losses_ally": c.losses_ally,
                "wins_enemy": c.wins_enemy,
                "losses_enemy": c.losses_enemy,
                "pA_tilde": pA_tilde,
                "pE_tilde": pE_tilde,
                "wA": wA,
                "threat": threat,
                "b_minus_you": b_minus_you,
                "b_minus_you_when_held": b_minus_you_when_held,
                "b_minus_you_when_not_held": b_minus_you_when_not_held,
                "ban_behavior_lift_vs_not_held": ban_behavior_lift_vs_not_held,
                "ban_priority": ban_priority,
            }
        )

    rows.sort(key=lambda row: row["ban_priority"], reverse=True)
    return rows


def _other_9_unique_bans(match: MatchRow) -> set:
    normalized_non_empty_bans = [ban.strip() for ban in match.bans if ban and ban.strip()]
    non_no_ban_bans = [ban for ban in normalized_non_empty_bans if ban.lower() != "no ban"]

    # If player ban is unknown/empty, fall back to using the full 10-ban row.
    if not match.player_ban:
        return set(non_no_ban_bans)

    player_ban_normalized = match.player_ban.strip()
    if player_ban_normalized.lower() == "no ban":
        return set(non_no_ban_bans)

    # Bias correction: remove one instance of the player's own ban from the 10-ban list
    # so b_minus_you estimates "banned by the other 9 players".
    remaining_bans = list(non_no_ban_bans)
    try:
        remaining_bans.remove(player_ban_normalized)
    except ValueError:
        # If the supplied player ban is not present, keep all observed bans.
        pass

    return set(remaining_bans)


def _write_output(rows: List[Dict[str, float]], output_file: Path) -> None:
    fieldnames = [
        "champion",
        "matches_analyzed",
        "n_ally",
        "n_enemy",
        "wins_ally",
        "losses_ally",
        "wins_enemy",
        "losses_enemy",
        "pA_tilde",
        "pE_tilde",
        "wA",
        "threat",
        "b_minus_you",
        "b_minus_you_when_held",
        "b_minus_you_when_not_held",
        "ban_behavior_lift_vs_not_held",
        "ban_priority",
    ]

    with output_file.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _print_preview(rows: List[Dict[str, float]], limit: int = 15) -> None:
    print("\nTop ban priority champions:")
    print(f"{'Rank':<6}{'Champion':<20}{'BanPriority':>12}{'Threat':>12}{'B-Other9':>12}")

    for index, row in enumerate(rows[:limit], start=1):
        print(
            f"{index:<6}{row['champion']:<20}{row['ban_priority']:>12.4f}"
            f"{row['threat']:>12.4f}{row['b_minus_you']:>12.4f}"
        )


def _read_positive_int(prompt: str, default: int) -> int:
    raw = input(f"{prompt} [{default}]: ").strip()
    if raw == "":
        return default
    value = int(raw)
    if value <= 0:
        raise ValueError("Value must be positive.")
    return value


def main() -> None:
    print("=== Ban Priority Metric Calculator ===")
    player_champion = input("Player champion to analyze (exact champion name): ").strip()
    if not player_champion:
        raise ValueError("Champion name is required.")

    match_count = _read_positive_int("How many recent matches to analyze", 50)

    matches = _read_matches(INPUT_FILE)
    recent_window = _select_recent_window(matches, match_count)
    selected = _filter_matches_by_champion(recent_window, player_champion)

    if not selected:
        print(
            f"No rows found in the last {match_count} rows of {INPUT_FILE} where "
            f"the player champion is '{player_champion}'."
        )
        return

    rows = _compute_ban_priority_rows(selected, recent_window)
    _write_output(rows, OUTPUT_FILE)

    print(
        f"Analyzed {len(selected)} match(es) for champion '{player_champion}'. "
        f"Wrote {len(rows)} champion rows to {OUTPUT_FILE}."
    )
    _print_preview(rows)


if __name__ == "__main__":
    main()
