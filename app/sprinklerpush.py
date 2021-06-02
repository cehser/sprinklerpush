import requests
import json
import redis
import pause
from datetime import datetime, timedelta, date, time
from pathlib import Path
# ospri_base = 'http://192.168.29.137'

# read and parse config file
p = Path(__file__).parent.joinpath('config', 'config.json')
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

def logMessage(mapped_log, water_level):
  title = 'OpenSprinkler'
  message = f'Bewässerung für <a href="{config["opensprinkler"]["base_uri"]}">{config["opensprinkler"]["name"]}</a>: \nProgramm <b>{mapped_log["program"]}</b> startete Kreis <b>{mapped_log["station"]}</b> um <b>{mapped_log["start"].strftime("%H:%M:%S")}</b> für <b>{str(mapped_log["duration"])}.</b>\nWL {water_level}%'
  pushMessage(title, message, mapped_log["start"].timestamp())

def json_serial(obj):
  """JSON serializer for objects not serializable by default json code"""

  if isinstance(obj, (datetime, date)):
    return obj.isoformat()
  elif isinstance(obj, (timedelta)):
    return obj.total_seconds()
  raise TypeError ("Type %s not serializable" % type(obj))

cache = redis.Redis(host=config['redis']['host'], port=config['redis']['port'])

while True:
  # get data from opensprinkler

  r_logs = requests.get(f'{config["opensprinkler"]["base_uri"]}{ospri_logs}&hist=1')
  r_all  = requests.get(f'{config["opensprinkler"]["base_uri"]}{ospri_all}')

  logs        = r_logs.json()
  water_level = r_all.json()['options']['wl']
  snames		  = r_all.json()['stations']['snames']
  programs 	  = r_all.json()['programs']['pd']

  # map logs to be better processible
  mapped_logs = list(map(lambda event : {'program': 'manuell' if event[0] == 99 else programs[event[0]-1][5], 'station':snames[event[1]], 'duration':timedelta(seconds=event[2]), 'start':datetime.utcfromtimestamp(event[3] - event[2])}, logs))

  cache.set('wl', water_level)

  # push water level message when configured time has passed and was not yet pushed today
  check_wl_time = time.fromisoformat(config['script']['check_wl_time'])
  last_wl_push = cache.get('last_wl_push')
  if((datetime.combine(date.today(), check_wl_time)-datetime.now()).total_seconds() < 0 and last_wl_push != date.today().isoformat().encode()):
    waterLevelMessage(water_level)
    cache.set('last_wl_push', date.today().isoformat())

  # push new log messages only
  for log in mapped_logs:
    key = 'log:' + log['start'].date().isoformat()
    value = json.dumps(log, default=json_serial)

    if(cache.sismember(key, value)):
      print (f'already pushed log message {value}')
    else: 
      logMessage(log, water_level)
      cache.sadd(key, value)
    cache.expire(key, 172800)

  pause.seconds(config['script']['check_interval'])
