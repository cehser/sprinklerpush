import requests
import json
from datetime import datetime, timedelta, date, time
from pathlib import Path
# ospri_base = 'http://192.168.29.137'

# read and parse config file
p = Path(__file__).with_name('config.json')
with p.open('r') as myfile:
  data=myfile.read()
config = json.loads(data)

# OpenSprinker API endpoints
ospri_logs = f'/jl?pw={config["opensprinkler"]["pw"]}'
ospri_all  = f'/ja?pw={config["opensprinkler"]["pw"]}'


def pushMessage(title, message, timestamp=datetime.now().timestamp()):
  data = {'token':config['pushover']['apptoken'], 
    'user':config['pushover']['userkey'], 
    'html':1, 
    'title':title, 
    'message': message,
    'timestamp': int(timestamp)
  }
  requests.post(config['pushover']['uri'], data)

def waterLevelMessage(water_level):
  title = 'OpenSprinkler'
  message = f'Aktueller Water Level für <a href="{config["opensprinkler"]["base_uri"]}">{config["opensprinkler"]["name"]}</a>: <b>{water_level}%</b>'
  pushMessage(title, message)

def logMessage(mapped_log):
  title = 'OpenSprinkler'
  message = f'Bewässerung für <a href="{config["opensprinkler"]["base_uri"]}">{config["opensprinkler"]["name"]}</a>: \nProgramm <b>{mapped_log["program"]}</b> startete Kreis <b>{mapped_log["station"]}</b> um <b>{mapped_log["start"].strftime("%H:%M:%S")}</b> für <b>{str(mapped_log["duration"])}.</b>'
  pushMessage(title, message, mapped_log["start"].timestamp())

# get data from opensprinkler

r_logs = requests.get(f'{config["opensprinkler"]["base_uri"]}{ospri_logs}&hist=1')
r_all  = requests.get(f'{config["opensprinkler"]["base_uri"]}{ospri_all}')

water_level = r_all.json()['options']['wl']
snames		= r_all.json()['stations']['snames']
programs 	= r_all.json()['programs']['pd']

logs = r_logs.json()
mapped_logs = list(map(lambda event : {'program': 'manuell' if event[0] == 99 else programs[event[0]-1][5], 'station':snames[event[1]], 'duration':timedelta(seconds=event[2]), 'start':datetime.utcfromtimestamp(event[3] - event[2])}, logs))


check_wl_time = time.fromisoformat(config['script']['check_wl_time'])

if(abs((datetime.combine(date.today(), check_wl_time)-datetime.now()).total_seconds()) < config["script"]["check_interval"]):
  waterLevelMessage(water_level)

for log in mapped_logs:
  if ((datetime.now() - log['start'] - log['duration']).total_seconds() < config["script"]["check_interval"]):
    logMessage(log)
