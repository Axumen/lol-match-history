import os
from pathlib import Path

# --- Riot API settings (used by get_match.py) ---
API_KEY = os.getenv("RIOT_API_KEY", "")
PUUID = os.getenv("RIOT_PUUID", "")
PRE_URL = os.getenv(
    "RIOT_MATCH_API_PREFIX",
    "https://americas.api.riotgames.com/lol/match/v5/matches/",
)
DATA_DRAGON_VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json"
DATA_DRAGON_CHAMPIONS_URL = (
    "https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/champion.json"
)
NO_BAN_LABEL = "No Ban"

# --- Champion-select defaults (used by champion_select_metric.py) ---
# Set these once, then the interactive tool only needs visible ally/enemy champions.
CHAMPION_SELECT_DEFAULT_ROLE = "MID"
CHAMPION_SELECT_DEFAULT_CONTEXT = None
CHAMPION_SELECT_DEFAULT_CANDIDATES = ["Ahri", "Syndra", "Vex"]
CHAMPION_SELECT_DEFAULT_INPUT_FILE = Path("Output.csv")
CHAMPION_SELECT_DEFAULT_MATCH_COUNT = 200
CHAMPION_SELECT_DEFAULT_INCLUDE_FUTURE_UNCERTAINTY = True

# --- Ban-priority defaults (used by ban_priority_metric.py) ---
# Modes:
# - "recent_window": analyze last N matches
# - "champion_appearances": scan descending matches until champion appears N times
BAN_PRIORITY_DEFAULT_ANALYSIS_MODE = "recent_window"
BAN_PRIORITY_DEFAULT_MAX_SCAN_MATCHES = 500
