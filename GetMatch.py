import json
import os
import time

import requests

PUUID = "A-KvvSAUCZsntcUJNiDJUV14oVGjCQFKzJj5k-rv6i5aAOFPfHq_W_t2516OpOh9-O1w8NzP5UcIGg"
# App - A-KvvSAUCZsntcUJNiDJUV14oVGjCQFKzJj5k-rv6i5aAOFPfHq_W_t2516OpOh9-O1w8NzP5UcIGg Symphony
# Dev - 7M50jVmrCSnHzJ9drVDkUIgzjKLlD2tZJwgjS0gxBJf-0HWxIlh3I4SWYd8A1iTw8VKy3OllBoK-cA
PRE_URL = "https://sea.api.riotgames.com/lol/match/v5/matches/"
API_KEY = "RGAPI-f4864035-c4a1-4b46-b887-333f5ed01a61"


def retrieve_match(start_index=0, count=20):
    match_ids_url = (
        f"{PRE_URL}by-puuid/{PUUID}/ids"
        f"?queue=420&type=ranked&start={start_index}&count={count}&api_key={API_KEY}"
    )
    match_ids = requests.get(match_ids_url).json()

    for match_id in match_ids:
        api_url = f"{PRE_URL}{match_id}?api_key={API_KEY}"
        response = requests.get(api_url)
        match_data = response.json()

        print(f"{match_id}.json")

        with open(f"{match_id}.json", "w") as json_file:
            json.dump(match_data, json_file, indent=4)


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
    champion_bans = [champion_id for _, champion_id in bans_by_turn]

    while len(champion_bans) < 10:
        champion_bans.append(-1)

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

    for champion_id in _extract_bans(data["info"].get("teams", [])):
        bans.append(champion_id)


def print_csv():
    file_count = 0
    champions = []
    match_meta = []
    bans = []

    for entry in os.listdir():
        if not entry.endswith(".json"):
            continue

        file_count += 1
        with open(entry, "r") as json_file:
            data = json.load(json_file)
            _append_match_data(data, match_meta, champions, bans)

    print(file_count, " Matches")

    with open("Output.csv", "w") as csv_file:
        for row in range(file_count):
            meta_start = row * 5
            champs_start = row * 10
            bans_start = row * 10

            for i in range(meta_start, meta_start + 5):
                csv_file.write(f"{match_meta[i]},")

            for i in range(champs_start, champs_start + 10):
                csv_file.write(f"{champions[i]},")

            for i in range(bans_start, bans_start + 10):
                csv_file.write(f"{bans[i]},")

            csv_file.write("\n")


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

        print("\nSleeping for 2 mins...")
        time.sleep(125)


def main():
    print("Match Index Start:")
    start_index = int(input())
    print("Number of Matches:")
    count = int(input())

    fetch_all_matches(start_index, count)

    print("\nOutput:")
    print_csv()


if __name__ == "__main__":
    main()
