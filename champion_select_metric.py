import argparse
import csv
import json
import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from api_config import (
    CHAMPION_SELECT_DEFAULT_CANDIDATES,
    CHAMPION_SELECT_DEFAULT_CONTEXT,
    CHAMPION_SELECT_DEFAULT_INCLUDE_FUTURE_UNCERTAINTY,
    CHAMPION_SELECT_DEFAULT_INPUT_FILE,
    CHAMPION_SELECT_DEFAULT_MATCH_COUNT,
    CHAMPION_SELECT_DEFAULT_ROLE,
)

INPUT_FILE = CHAMPION_SELECT_DEFAULT_INPUT_FILE
EPSILON = 1e-9


@dataclass
class MatchRow:
    game_id: str
    player_win: bool
    allies: List[str]
    enemies: List[str]


def _safe_sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1 / (1 + z)
    z = math.exp(x)
    return z / (1 + z)


def _smoothed_rate(wins: int, losses: int, baseline: float, k: float = 8.0) -> float:
    n = wins + losses
    return (wins + k * baseline) / (n + k)


def _read_matches(path: Path) -> List[MatchRow]:
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    rows: List[MatchRow] = []
    with path.open("r", newline="") as f:
        reader = csv.reader(f)
        for row_number, row in enumerate(reader, start=1):
            if len(row) < 15:
                raise ValueError(
                    f"Row {row_number} has {len(row)} columns; expected at least 15 "
                    "(5 metadata + 10 champions)."
                )

            champions = [champ.strip() for champ in row[5:15]]
            rows.append(
                MatchRow(
                    game_id=str(row[1]).strip(),
                    player_win=str(row[2]).strip().lower() == "true",
                    allies=champions[:5],
                    enemies=champions[5:],
                )
            )

    return rows


def _validate_required_input(
    ally_faceup_champions: Sequence[str],
    enemy_faceup_champions: Sequence[str],
    candidate_champions: Sequence[str],
) -> None:
    if ally_faceup_champions is None:
        raise ValueError("ally_faceup_champions must be provided before computation.")
    if enemy_faceup_champions is None:
        raise ValueError("enemy_faceup_champions must be provided before computation.")
    if candidate_champions is None:
        raise ValueError("candidate_champions must be provided before computation.")


def _canonical(champion: str) -> str:
    return champion.strip().lower()


def _team_contains(team: Iterable[str], champion: str) -> bool:
    key = _canonical(champion)
    return any(_canonical(c) == key for c in team)


def _pair_synergy_score(
    matches: Sequence[MatchRow],
    candidate: str,
    ally: str,
    baseline: float,
) -> float:
    wins = 0
    losses = 0

    for match in matches:
        if _team_contains(match.allies, candidate) and _team_contains(match.allies, ally):
            if match.player_win:
                wins += 1
            else:
                losses += 1

    p = _smoothed_rate(wins, losses, baseline)
    centered = p - 0.5
    magnitude = math.log1p(abs(centered) * 8.0)
    return math.copysign(magnitude, centered)


def _pair_enemy_pressure_score(
    matches: Sequence[MatchRow],
    candidate: str,
    enemy: str,
    baseline: float,
) -> float:
    wins = 0
    losses = 0

    for match in matches:
        if _team_contains(match.allies, candidate) and _team_contains(match.enemies, enemy):
            if match.player_win:
                wins += 1
            else:
                losses += 1

    p = _smoothed_rate(wins, losses, baseline)
    centered = p - 0.5
    # Maps centered win delta to a bounded pressure/advantage style value.
    return _safe_sigmoid(6.0 * centered) - 0.5


def _matchup_interaction(
    matches: Sequence[MatchRow],
    candidate: str,
    unseen: str,
    baseline: float,
) -> float:
    # Reuse enemy-pressure estimate as the interaction primitive.
    return _pair_enemy_pressure_score(matches, candidate, unseen, baseline)


def _future_uncertainty_term(
    matches: Sequence[MatchRow],
    candidate: str,
    ally_faceup_champions: Sequence[str],
    enemy_faceup_champions: Sequence[str],
    candidate_champions: Sequence[str],
    baseline: float,
    top_k: int = 12,
) -> float:
    visible = {_canonical(ch) for ch in ally_faceup_champions}
    visible.update(_canonical(ch) for ch in enemy_faceup_champions)
    visible.update(_canonical(ch) for ch in candidate_champions)

    counts: Counter = Counter()
    total_slots = 0
    for match in matches:
        for champ in match.allies + match.enemies:
            key = _canonical(champ)
            if key in visible:
                continue
            counts[champ] += 1
            total_slots += 1

    if not counts or total_slots == 0:
        return 0.0

    most_common = counts.most_common(top_k)
    raw = 0.0
    weight_total = 0.0
    for unseen, count in most_common:
        weight = count / total_slots
        raw += weight * _matchup_interaction(matches, candidate, unseen, baseline)
        weight_total += weight

    if weight_total <= EPSILON:
        return 0.0
    return raw / weight_total


def _game_id_sort_key(game_id: str):
    game_id_str = str(game_id).strip()
    try:
        return int(game_id_str)
    except ValueError:
        return game_id_str


def _select_recent_window(matches: Sequence[MatchRow], max_matches: int) -> List[MatchRow]:
    if max_matches <= 0:
        return []
    return sorted(matches, key=lambda m: _game_id_sort_key(m.game_id), reverse=True)[:max_matches]


def generate_champion_select_recommendations(
    *,
    player_role: str,
    player_champion_context: Optional[str],
    ally_faceup_champions: Sequence[str],
    enemy_faceup_champions: Sequence[str],
    candidate_champions: Sequence[str],
    input_file: Path = INPUT_FILE,
    match_count: int = 200,
    include_future_uncertainty: bool = True,
) -> Dict[str, object]:
    _validate_required_input(
        ally_faceup_champions=ally_faceup_champions,
        enemy_faceup_champions=enemy_faceup_champions,
        candidate_champions=candidate_champions,
    )

    if not candidate_champions:
        raise ValueError("candidate_champions must include at least one champion.")
    if match_count <= 0:
        raise ValueError("match_count must be positive.")

    all_matches = _read_matches(input_file)
    recent_matches = _select_recent_window(all_matches, match_count)
    if not recent_matches:
        raise ValueError(f"No matches available in {input_file} to compute pick recommendations.")

    baseline = sum(1 for m in recent_matches if m.player_win) / len(recent_matches)

    rankings: List[Dict[str, object]] = []
    for candidate in candidate_champions:
        ally_terms: List[Tuple[str, float]] = []
        enemy_terms: List[Tuple[str, float]] = []

        for ally in ally_faceup_champions:
            ally_terms.append(
                (ally, _pair_synergy_score(recent_matches, candidate, ally, baseline))
            )

        for enemy in enemy_faceup_champions:
            enemy_terms.append(
                (enemy, _pair_enemy_pressure_score(recent_matches, candidate, enemy, baseline))
            )

        u_value = (
            _future_uncertainty_term(
                matches=recent_matches,
                candidate=candidate,
                ally_faceup_champions=ally_faceup_champions,
                enemy_faceup_champions=enemy_faceup_champions,
                candidate_champions=candidate_champions,
                baseline=baseline,
            )
            if include_future_uncertainty
            else 0.0
        )

        v_value = sum(score for _, score in ally_terms) + sum(score for _, score in enemy_terms) + u_value

        rankings.append(
            {
                "champion": candidate,
                "score": v_value,
                "ally_terms": [{"ally": ally, "score": score} for ally, score in ally_terms],
                "enemy_terms": [{"enemy": enemy, "score": score} for enemy, score in enemy_terms],
                "future_uncertainty": u_value,
            }
        )

    rankings.sort(key=lambda row: row["score"], reverse=True)

    return {
        "player_role": player_role,
        "player_champion_context": player_champion_context,
        "matches_analyzed": len(recent_matches),
        "pick": rankings[0]["champion"],
        "rankings": rankings,
    }


def _parse_csv_list(raw: str) -> List[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def _prompt_required_list(label: str) -> List[str]:
    while True:
        raw = input(f"{label} (comma-separated): ").strip()
        parsed = _parse_csv_list(raw)
        if parsed:
            return parsed
        print(f"{label} is required and must include at least one champion.")


def _collect_inputs_step_by_step(args: argparse.Namespace) -> argparse.Namespace:
    print("=== Champion Select Draft Scorer ===")
    print("Using defaults from api_config.py for role/candidates/options.")
    print("Only ally and enemy visible champions are requested.\n")

    if args.include_future_uncertainty and args.no_future_uncertainty:
        raise ValueError(
            "Choose only one of --include-future-uncertainty or --no-future-uncertainty."
        )

    print("Using defaults from api_config.py for role/candidates/options.")
    print("Only ally and enemy visible champions are requested.\n")

    role = args.role or CHAMPION_SELECT_DEFAULT_ROLE
    context = args.context if args.context is not None else CHAMPION_SELECT_DEFAULT_CONTEXT
    allies = args.allies if args.allies is not None else ",".join(
        _prompt_required_list("1) Visible ally champions")
    )
    enemies = args.enemies if args.enemies is not None else ",".join(
        _prompt_required_list("2) Visible enemy champions")
    )
    candidates = args.candidates if args.candidates is not None else ",".join(
        CHAMPION_SELECT_DEFAULT_CANDIDATES
    )

    if not _parse_csv_list(candidates):
        raise ValueError(
            "No candidate champions configured. Set CHAMPION_SELECT_DEFAULT_CANDIDATES in api_config.py "
            "or pass --candidates."
        )

    input_file = args.input_file or INPUT_FILE
    match_count = args.match_count or CHAMPION_SELECT_DEFAULT_MATCH_COUNT
    if args.include_future_uncertainty:
        include_future_uncertainty = True
    elif args.no_future_uncertainty:
        include_future_uncertainty = False
    else:
        include_future_uncertainty = CHAMPION_SELECT_DEFAULT_INCLUDE_FUTURE_UNCERTAINTY

    args.role = role
    args.context = context
    args.allies = allies
    args.enemies = enemies
    args.candidates = candidates
    args.input_file = input_file
    args.match_count = match_count
    args.no_future_uncertainty = not include_future_uncertainty
    return args


def _print_rankings_summary_table(result: Dict[str, object]) -> None:
    rankings = result.get("rankings", [])
    if not rankings:
        print("No candidate rankings to display.")
        return

    print("\n=== Summary Table (All Candidates) ===")
    headers = ["Rank", "Candidate", "V(c|S_t)", "Ally ΣA", "Enemy ΣE", "U(c)"]
    row_format = "{:<6}{:<18}{:>12}{:>12}{:>12}{:>12}"
    print(row_format.format(*headers))

    for index, row in enumerate(rankings, start=1):
        ally_sum = sum(term["score"] for term in row.get("ally_terms", []))
        enemy_sum = sum(term["score"] for term in row.get("enemy_terms", []))
        u_value = float(row.get("future_uncertainty", 0.0))
        total = float(row.get("score", 0.0))
        print(
            row_format.format(
                index,
                str(row.get("champion", ""))[:17],
                f"{total:.4f}",
                f"{ally_sum:.4f}",
                f"{enemy_sum:.4f}",
                f"{u_value:.4f}",
            )
        )

    print(f"\nRecommended pick: {result.get('pick')}")


def _print_candidate_value_breakdown(result: Dict[str, object]) -> None:
    rankings = result.get("rankings", [])
    if not rankings:
        return

    print("\n=== Per-Candidate Calculated Values ===")
    for index, row in enumerate(rankings, start=1):
        champion = row.get("champion", "")
        total = float(row.get("score", 0.0))
        u_value = float(row.get("future_uncertainty", 0.0))
        ally_terms = row.get("ally_terms", [])
        enemy_terms = row.get("enemy_terms", [])

        print(f"\n[{index}] {champion}")
        print(f"  V(c|S_t): {total:.6f}")
        print(f"  U(c):     {u_value:.6f}")

        if ally_terms:
            print("  Ally terms:")
            for term in ally_terms:
                print(f"    - A({champion}, {term['ally']}): {float(term['score']):.6f}")
        else:
            print("  Ally terms: (none)")

        if enemy_terms:
            print("  Enemy terms:")
            for term in enemy_terms:
                print(f"    - E({champion}, {term['enemy']}): {float(term['score']):.6f}")
        else:
            print("  Enemy terms: (none)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Compute asymmetric draft pick recommendations from Output.csv match history. "
            "Runs as a minimal step-by-step TUI by default."
        )
    )
    parser.add_argument("--role", default=None, help="Optional override for role.")
    parser.add_argument("--context", default=None, help="Optional override for champion context.")
    parser.add_argument("--allies", help="Comma-separated visible ally champions.")
    parser.add_argument("--enemies", help="Comma-separated visible enemy champions.")
    parser.add_argument("--candidates", default=None, help="Optional override for candidate champions.")
    parser.add_argument(
        "--input-file",
        type=Path,
        default=None,
        help=f"Optional override for input CSV path (default from api_config.py: {INPUT_FILE}).",
    )
    parser.add_argument(
        "--match-count",
        type=int,
        default=None,
        help=(
            "Optional override for recent-match window "
            f"(default from api_config.py: {CHAMPION_SELECT_DEFAULT_MATCH_COUNT})."
        ),
    )
    parser.add_argument(
        "--include-future-uncertainty",
        action="store_true",
        help="Force-enable optional U(c) term.",
    )
    parser.add_argument(
        "--no-future-uncertainty",
        action="store_true",
        help="Force-disable optional U(c) term.",
    )

    args = parser.parse_args()
    args = _collect_inputs_step_by_step(args)

    result = generate_champion_select_recommendations(
        player_role=args.role,
        player_champion_context=args.context,
        ally_faceup_champions=_parse_csv_list(args.allies),
        enemy_faceup_champions=_parse_csv_list(args.enemies),
        candidate_champions=_parse_csv_list(args.candidates),
        input_file=args.input_file,
        match_count=args.match_count,
        include_future_uncertainty=not args.no_future_uncertainty,
    )

    _print_rankings_summary_table(result)
    _print_candidate_value_breakdown(result)
    print("\n=== Raw JSON ===")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
