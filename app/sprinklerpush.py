import requests
import json
import redis
import pause
import logging
from datetime import datetime, timedelta, date, time
from pathlib import Path
from funcy import omit

# read and parse config file
p = Path(__file__).parent.joinpath('config', 'config.json')
with p.open('r') as myfile:
  data=myfile.read()
config = json.loads(data)

loglevel = config["script"]["loglevel"]
print(f"LOG LEVEL: {loglevel}")
logging.basicConfig(level=logging.getLevelName(loglevel))

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
  title = 'OpenSprinkler - Neuer Water Level'
  message = f'Aktueller Water Level für <a href="{config["opensprinkler"]["base_uri"]}">{config["opensprinkler"]["name"]}</a>: <b>{water_level}%</b>'
  pushMessage(title, message)

def statusMessage(mapped_status, water_level):
  title = 'OpenSprinkler - Bewässerung gestartet'

  message = f'''Bewässerung für <a href="{config["opensprinkler"]["base_uri"]}">{config["opensprinkler"]["name"]}</a>:
Programm <b>{mapped_status["status"]["program"]}</b> startete Kreis <b>{mapped_status["station"]}</b> um <b>{mapped_status["status"]["start"].strftime("%H:%M:%S")}</b>.
Bewässerungszeit <b>{str(mapped_status["status"]["duration"])}</b> (WL {water_level}%).'''

  pushMessage(title, message, mapped_status["status"]["start"].timestamp())

def logMessage(mapped_log, water_level):
  title = 'OpenSprinkler - Bewässerung gestoppt'

  message = f'''Bewässerung für <a href="{config["opensprinkler"]["base_uri"]}">{config["opensprinkler"]["name"]}</a>:
Programm <b>{mapped_log["program"]}</b> stoppte Kreis <b>{mapped_log["station"]}</b> um <b>{mapped_log["end"].strftime("%H:%M:%S")}</b>.
Bewässerungszeit <b>{str(mapped_log["duration"])}</b> (WL {water_level}%).'''

  pushMessage(title, message, mapped_log["end"].timestamp())


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
  status      = r_all.json()['settings']['ps']
  sbits       = r_all.json()['settings']['sbits']
  now         = datetime.utcfromtimestamp(r_all.json()['settings']['devt']) # device time needed to calculate total duration based on time left

  # map logs to be better processible
  mapped_logs = list(map(lambda event : {'program': 'manuell' if event[0] == 99 else programs[event[0]-1][5], 'station':snames[event[1]], 'duration':timedelta(seconds=event[2]), 'end':datetime.utcfromtimestamp(event[3])}, logs))


  mapped_status = [
    {
      'station': snames[i], 
      'status': { 
        'running': (1<<i)&sbits[0]>0, # i-th bit is 1 iff station is active
        'program': 'manuell' if prog == 99 else programs[prog-1][5], 
        'start':datetime.utcfromtimestamp(start),  
        'left':timedelta(seconds=int(left)),
        'duration': now - datetime.utcfromtimestamp(int(start - left))
      }
    } for i,[prog,left,start] in enumerate(status)
  ]

  cache.set('wl', water_level)

  # push water level message when configured time has passed and was not yet pushed today
  check_wl_time = time.fromisoformat(config['script']['check_wl_time'])
  last_wl_push = cache.get('last_wl_push')
  if((datetime.combine(date.today(), check_wl_time)-datetime.now()).total_seconds() < 0 and last_wl_push != date.today().isoformat().encode()):
    waterLevelMessage(water_level)
    cache.set('last_wl_push', date.today().isoformat())

  # push new log messages only
  for log in mapped_logs:
    key = 'log:' + log['end'].date().isoformat()
    value = json.dumps(log, default=json_serial)

    if(cache.sismember(key, value)):
      logging.debug(f'already pushed log message {value}')
    else: 
      logMessage(log, water_level)
      cache.sadd(key, value)
    cache.expire(key, 172800)

  # push new status messages only
  for status in mapped_status:
    logging.info('status: ' + json.dumps(status, default=json_serial))
    key = 'status:' + status['station']
    #remove time left and duration
    value = json.dumps({'station':status['station'], 'status':omit(status['status'],('left', 'duration'))}, default=json_serial)
    if(status['status']['running'] and cache.get(key) != value.encode()):
      logging.debug (f'pushing status message {value}') 
      statusMessage(status, water_level)
      cache.set(key, value)
    else:
      logging.debug(f'not pushing status message {value}') 
      

  pause.seconds(config['script']['check_interval'])
