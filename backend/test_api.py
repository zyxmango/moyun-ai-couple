import requests, json
BASE = 'https://rebalance-geology-collected.ngrok-free.dev'
H = {'ngrok-skip-browser-warning': 'true'}

login = requests.post(f'{BASE}/api/auth/login', json={'email':'1@1.com','password':'123456'}, headers=H, timeout=10)
print('LOGIN:', login.status_code, login.text[:200])
if login.status_code != 200:
    exit()

token = login.json().get('token','')
TH = {**H, 'Authorization': 'Bearer ' + token}

album = requests.get(f'{BASE}/api/album', headers=TH, timeout=10)
print('ALBUM:', album.status_code)
if album.status_code == 200:
    data = album.json()
    print('COUNT:', len(data))
    if data:
        first = data[0]
        print('FIRST KEYS:', list(first.keys()))
        print('FIRST URL:', first.get('url',''))
        print('FIRST JSON:', json.dumps(first, ensure_ascii=False)[:500])

info = requests.get(f'{BASE}/api/couple/info', headers=TH, timeout=10)
print('COUPLE:', info.status_code)
if info.status_code == 200:
    d = info.json()
    print('KEYS:', list(d.keys()))
    print('hero_bg:', d.get('hero_bg',''))
    print('chat_bg:', d.get('chat_bg',''))

me = requests.get(f'{BASE}/api/auth/me', headers=TH, timeout=10)
print('ME:', me.status_code)
if me.status_code == 200:
    d = me.json()
    print('avatar:', d.get('avatar',''))
