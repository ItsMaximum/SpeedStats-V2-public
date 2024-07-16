import json
import csv
import math
from datetime import datetime
import mysql.connector as mariadb
import sys
import logging
import os
import sys

excludedPlayers = []

_log = logging.getLogger('SpeedStats-V2')

def collectGroups(path: str):
    groups = {}
    with open(path, 'r') as file:
        runs = json.load(file)
        _log.info(len(runs))
        for run in runs:
            if run.get('groupName') not in groups:
                groups[run.get('groupName')] = [run]
            else:
                groups[run.get('groupName')].append(run)
    return groups

def findNumWRs(runs: list):
    reverseTime = runs[0]['isReverseTime']
    dateSortedRuns = sorted(runs, key=lambda run: (run['date'], run['dateSubmitted']))
    currentWR = -1
    numWRs = 0
    for run in dateSortedRuns:
        if run['date'] <= 0 or run['time'] == None: # date or time is null
            continue
        
        if currentWR == -1 or (reverseTime and run['time'] > currentWR) or (not reverseTime and run['time'] < currentWR):
            currentWR = run['time']
            numWRs += 1
    return numWRs

def buildLeaderboard(runs: list):  
    dateSortedRuns = sorted(runs, key=lambda run: (run['date'], run['dateSubmitted']))
    
    reverseTime = runs[0]['isReverseTime']
    fullySortedRuns = sorted(dateSortedRuns, reverse = reverseTime, key = lambda run: (run['time']))
    
    uniquePlayerNames = []
    leaderboard = []
    
    for run in fullySortedRuns:
        if run.get('playerNames') not in uniquePlayerNames:
            uniquePlayerNames.append(run.get('playerNames'))
            leaderboard.append(run)
    
    return leaderboard

def processGroups(groups: dict):
    leaderboards = []
    for groupName, runs in groups.items():
        
        leaderboard = buildLeaderboard(runs)
        numWRs = findNumWRs(runs)
        leaderboardRuns = len(leaderboard)
        totalRuns = len(runs)
        WRValue = (math.log(totalRuns, 1.7) * numWRs + 120 * math.exp(-100 / totalRuns) + 0.04 * totalRuns) * (1 - (numWRs + 1) / (totalRuns + leaderboardRuns))
        sf = (math.log(leaderboardRuns, 10) / leaderboardRuns) + 0.001 if leaderboardRuns > 2 else 0.2
        previousRun = None
        currPlace = leaderboardRuns

        for run in reversed(leaderboard):
            if previousRun != None and previousRun['time'] == run['time']:
                run['place'] = previousRun['place']
            else:
                run['place'] = currPlace

            top = sf * WRValue * (leaderboardRuns + 1 - run['place'])
            bottom = run['place'] + (sf * leaderboardRuns - 1)
            value = top / bottom

            if run['isLevelRun']:
                value *= 0.5

            run['value'] = value
            previousRun = run
            currPlace -= 1
        
        leaderboards.append(leaderboard)
    return leaderboards

def generateCSV(leaderboards: dict, csvPath: str):
    with open(csvPath, mode='w', encoding='utf-8', newline='\n') as file:
        writer = csv.writer(file, quoting=csv.QUOTE_ALL, lineterminator='\n')
        for leaderboard in leaderboards:

            name = leaderboard[0].get('groupName').replace("\\","\\\\")
            series = leaderboard[0].get('seriesName') 
            series = series.replace("\\","\\\\").replace(",", ".") if series != None else "\\N"
            game = leaderboard[0].get('gameName').replace("\\","\\\\")
            creditedPlayers = []

            for run in leaderboard:
                
                platform = run.get('platformName') if run.get('platformName') != None else "\\N"
                date = datetime.fromtimestamp(run.get('date')).strftime("%Y-%m-%d") if run.get('date') > 0 else "\\N"
                valuePerPlayer = (run.get('value') / len(run.get('playerNames')))
                valuePerPlayer = "{:.3f}".format(valuePerPlayer)
                
                for player in run.get('playerNames'):
                    isGuest = player == None or player[:7] == "[Guest]"
                    # Only credits players for their best run in co-op categories
                    if player not in creditedPlayers and player not in excludedPlayers and not isGuest:
                        creditedPlayers.append(player)
                        params = [name, series, game, player, platform, run.get('place'), valuePerPlayer, date]
                        writer.writerow(params)

def exportToDatabase(absPath: str):
    try:
        conn = mariadb.connect(
            host="localhost",
            port=3306,
            user="root",
            password = "",
            database="SpeedStats"
        )
    except mariadb.Error as e:
        _log.error(f"Error connecting to MariaDB Platform: {e}")
        sys.exit(1)

    try:
        cursor = conn.cursor()
        cursor.execute("TRUNCATE TABLE runs")
        cursor.execute(
            f"""
            LOAD DATA INFILE '{absPath}'
            INTO TABLE runs
            FIELDS TERMINATED BY ',' 
            ENCLOSED BY '\"' 
            ESCAPED BY '\"'
            LINES TERMINATED BY '\n'
            (Leaderboard, Series, Game, Player, Platform, Place, Value, Date);
            """)

        cursor.execute("TRUNCATE TABLE playerRanks")
        cursor.execute(
            f"""
            INSERT INTO playerRanks (Rank, Player, Points)
            SELECT ROW_NUMBER() OVER (ORDER BY Points DESC) AS Rank, t1.Player, t1.Points
            FROM (
                SELECT Player, SUM(Value) AS Points
                FROM runs
                GROUP BY Player
                ORDER BY Points DESC
            ) AS t1;
            """
        )

        conn.commit()
    except Exception as e:
        _log.error(e)

def processRuns(jsonPath: str, csvPath: str, exportToDatabase: bool):
    groups = collectGroups(jsonPath)
    leaderboards = processGroups(groups)
    generateCSV(leaderboards, csvPath)
    if exportToDatabase:
        absPath = os.path.join(os.getcwd(), csvPath)
        exportToDatabase(absPath)
