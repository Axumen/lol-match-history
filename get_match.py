import json
import os
import time

import requests

from api_config import (
    API_KEY,
    DATA_DRAGON_CHAMPIONS_URL,
    DATA_DRAGON_VERSIONS_URL,
    NO_BAN_LABEL,
    PRE_URL,
    PUUID,
)

_CHAMPION_ID_TO_NAME = None
OUTPUT_FILE = "Output.csv"
NEW_OUTPUT_FILE = "NewOutput.csv"


def _request_json(url):
    return requests.get(url).json()


def retrieve_match(start_index=0, count=20):
    match_ids_url = (
        f"{PRE_URL}by-puuid/{PUUID}/ids"
        f"?queue=420&type=ranked&start={start_index}&count={count}&api_key={API_KEY}"
    )
    match_ids = _request_json(match_ids_url)

    total = len(match_ids)
    for index, match_id in enumerate(match_ids, start=1):
        api_url = f"{PRE_URL}{match_id}?api_key={API_KEY}"
        match_data = _request_json(api_url)
        json_name = f"{match_id}.json"

        with open(json_name, "w") as json_file:
            json.dump(match_data, json_file, indent=4)

        print(f"  - Saved {index}/{total}: {json_name}")


def _get_champion_id_to_name_map():
    global _CHAMPION_ID_TO_NAME

    if _CHAMPION_ID_TO_NAME is not None:
        return _CHAMPION_ID_TO_NAME

    latest_version = _request_json(DATA_DRAGON_VERSIONS_URL)[0]
    champions_url = DATA_DRAGON_CHAMPIONS_URL.format(version=latest_version)
    champions_payload = _request_json(champions_url)

    _CHAMPION_ID_TO_NAME = {
        int(champion["key"]): champion["name"]
        for champion in champions_payload.get("data", {}).values()
    }

    return _CHAMPION_ID_TO_NAME


def _champion_id_to_name(champion_id):
    if champion_id is None or champion_id < 0:
        return NO_BAN_LABEL

    champion_id_to_name = _get_champion_id_to_name_map()
    return champion_id_to_name.get(champion_id, str(champion_id))


def _get_player_index(metadata_participants):
    player_index = 0
    while metadata_participants[player_index] != PUUID:
        player_index += 1
    return player_index


def _extract_bans(teams):
    bans_by_turn = []

    for team in teams:
        for ban in team.get("bans", []):
            bans_by_turn.append((ban.get("pickTurn", 999), ban.get("championId", -1)))

    bans_by_turn.sort(key=lambda item: item[0])
    champion_bans = [_champion_id_to_name(champion_id) for _, champion_id in bans_by_turn]

    while len(champion_bans) < 10:
        champion_bans.append(NO_BAN_LABEL)

    return champion_bans[:10]


def _append_match_data(data, match_meta, champions, bans):
    player_index = _get_player_index(data["metadata"]["participants"])
    participants = data["info"]["participants"]

    match_meta.append(data["info"]["gameVersion"])
    match_meta.append(data["info"]["gameId"])
    match_meta.append(str(participants[player_index]["win"]))
    match_meta.append(player_index)
    match_meta.append(participants[player_index]["championName"])

    if player_index < 5:
        for i in range(0, 10):
            champions.append(participants[i]["championName"])
    else:
        for i in range(5, 10):
            champions.append(participants[i]["championName"])
        for i in range(0, 5):
            champions.append(participants[i]["championName"])

    for champion_name in _extract_bans(data["info"].get("teams", [])):
        bans.append(champion_name)


def print_csv():
    file_count = 0
    champions = []
    match_meta = []
    bans = []
    existing_player_bans = _load_existing_player_bans()

    for entry in os.listdir():
        if not entry.endswith(".json"):
            continue

        file_count += 1
        with open(entry, "r") as json_file:
            data = json.load(json_file)
            _append_match_data(data, match_meta, champions, bans)

    print(f"[2/3] Building {NEW_OUTPUT_FILE} from {file_count} match file(s)...")

    row_order = sorted(
        range(file_count),
        key=lambda row: _game_id_sort_key(match_meta[row * 5 + 1]),
        reverse=True,
    )

    with open(NEW_OUTPUT_FILE, "w") as csv_file:
        for row in row_order:
            meta_start = row * 5
            champs_start = row * 10
            bans_start = row * 10
            game_id = str(match_meta[meta_start + 1])

            for i in range(meta_start, meta_start + 5):
                csv_file.write(f"{match_meta[i]},")

            for i in range(champs_start, champs_start + 10):
                csv_file.write(f"{champions[i]},")

            for i in range(bans_start, bans_start + 10):
                csv_file.write(f"{bans[i]},")

            preserved_player_ban = existing_player_bans.get(game_id, "")
            csv_file.write(f"{preserved_player_ban}\n")

    if os.path.exists(OUTPUT_FILE):
        os.remove(OUTPUT_FILE)
    os.rename(NEW_OUTPUT_FILE, OUTPUT_FILE)


def _game_id_sort_key(game_id):
    game_id_str = str(game_id).strip()
    try:
        return int(game_id_str)
    except ValueError:
        return game_id_str


def _load_existing_player_bans():
    if not os.path.exists(OUTPUT_FILE):
        return {}

    player_bans_by_game_id = {}
    with open(OUTPUT_FILE, "r") as csv_file:
        for line in csv_file:
            row = line.rstrip("\n").split(",")
            if len(row) < 2:
                continue

            game_id = row[1].strip()
            if game_id == "":
                continue

            # New format: player ban is the final column.
            player_ban = row[-1].strip() if len(row) >= 26 else ""
            player_bans_by_game_id[game_id] = player_ban

    return player_bans_by_game_id


def fetch_all_matches(start_index, count):
    if count <= 100:
        retrieve_match(start_index, count - 1)
        return

    while count > 0:
        interval = min(99, count)
        retrieve_match(start_index, interval)
        start_index += 100
        count -= 100

        if count <= 0:
            break

        print("\nRate limit cooldown: sleeping for 125 seconds...")
        time.sleep(125)


def _read_int(prompt_text, default):
    raw_value = input(f"{prompt_text} [{default}]: ").strip()
    if raw_value == "":
        return default
    return int(raw_value)


def main():
    print("=== League Match Export ===")
    print("Recommended: Start Index = 0, Number of Matches = 20")

    start_index = _read_int("Start Index", 0)
    count = _read_int("Number of Matches", 20)

    print("\n[1/3] Fetching match JSON files...")
    fetch_all_matches(start_index, count)

    print_csv()

    print("[3/3] Done.")
    print("Output file: Output.csv")
    print("Columns: 5 metadata + 10 champions + 10 bans + 1 player_ban")


if __name__ == "__main__":
    main()
