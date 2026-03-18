import requests
import json
import os
import time

puuid = "A-KvvSAUCZsntcUJNiDJUV14oVGjCQFKzJj5k-rv6i5aAOFPfHq_W_t2516OpOh9-O1w8NzP5UcIGg"
# App - A-KvvSAUCZsntcUJNiDJUV14oVGjCQFKzJj5k-rv6i5aAOFPfHq_W_t2516OpOh9-O1w8NzP5UcIGg Symphony
# Dev - 7M50jVmrCSnHzJ9drVDkUIgzjKLlD2tZJwgjS0gxBJf-0HWxIlh3I4SWYd8A1iTw8VKy3OllBoK-cA
pre_url = "https://sea.api.riotgames.com/lol/match/v5/matches/"
api_key = "RGAPI-f4864035-c4a1-4b46-b887-333f5ed01a61"

def retrive_Match(start_index = 0, count = 20):

    # matchid_list = "https://sea.api.riotgames.com/lol/match/v5/matches/by-puuid/7M50jVmrCSnHzJ9drVDkUIgzjKLlD2tZJwgjS0gxBJf-0HWxIlh3I4SWYd8A1iTw8VKy3OllBoK-cA/ids?queue=420&type=ranked&start=0&count=10&api_key=RGAPI-dcd858a1-1a21-4a66-9122-3a630b996424"
    matchid_list = pre_url + "by-puuid/" + puuid + "/ids?queue=420&type=ranked&start=" + str(start_index) +  "&count=" + str(count) + "&api_key=" + api_key

#    print(matchid_list)

    mid_list = requests.get(matchid_list).json()

    for x in mid_list:
        api_url = pre_url + x + "?api_key=" + api_key
        resp = requests.get(api_url)
        match_data = resp.json()
        match_data.keys()

        print(x + ".json")

        with open(x + ".json", 'w') as f:
            json.dump(match_data, f, indent=4)


list = []
metas = []
game_version = []

def print_CSV():

    file_count = 0

    dir_list = os.listdir()

    for match_json in dir_list:

        if match_json.endswith('.json'):

            file_count += 1

            with open(match_json, 'r') as f:

                data = json.load(f)

                game_version = str(data['info']['gameVersion'])



                i = 0

                while data['metadata']['participants'][i] != puuid:
                    i += 1

                metas.append(data['info']['gameVersion'])
                metas.append(data['info']['gameId'])
                metas.append(str(data['info']['participants'][i]['win']))
                metas.append(i)
                metas.append(data['info']['participants'][i]['championName'])

                if i < 5:
                    for j in range(0, 10, 1):
                        list.append(data['info']['participants'][j]['championName'])

                else:
                    for j in range(5, 10, 1):
                        list.append(data['info']['participants'][j]['championName'])

                    for j in range(0, 5, 1):
                        list.append(data['info']['participants'][j]['championName'])

            f.close()

    print(file_count, " Matches")

    with open('Output.csv', 'w') as fcsv:

        for i in range(0, file_count, 1):

            for j in range(i * 5, 5 * (i + 1), 1):
                fcsv.write(str(metas[j]))
                fcsv.write(",")

            for j in range(i * 10, 10 * (i + 1), 1):
                fcsv.write(list[j])
                fcsv.write(",")

            fcsv.write("\n")

    fcsv.close()

print("Match Index Start:")
start_index = int(input())
print("Number of Matches:")
count = int(input())

if count <= 100:

    retrive_Match(start_index, count - 1)

else:

    while count > 0:

        interval = min(99, count)
        retrive_Match(start_index, interval)
        start_index = start_index + 100
        count = count - 100

        if count > 0:
            pass
        else: break

        print("\nSleeping for 2 mins...")
        time.sleep(125)

print("\nOutput:")
print_CSV()

