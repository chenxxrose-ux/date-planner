"""每月找新店：用 Google 地圖 Places API (New) 文字搜尋，挑評論還不多但評價高的店，加進 data/places.json。
需要 GitHub Secret：GOOGLE_MAPS_KEY。沒有金鑰就只更新狀態、不做事。"""
import json, os, re, math, datetime, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
NOW = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
KEY = os.environ.get('GOOGLE_MAPS_KEY', '').strip()

HUBS = {'ks': (22.627, 120.32, '高雄'), 'tn': (22.997, 120.205, '台南'), 'pts': (22.669, 120.486, '屏東'), 'kt': (21.96, 120.78, '墾丁 恆春'),
        'cy': (23.479, 120.445, '嘉義市'), 'als': (23.51, 120.75, '阿里山'), 'ch': (24.07, 120.50, '彰化 鹿港'), 'tc': (24.15, 120.67, '台中'),
        'nt': (23.90, 120.95, '日月潭'), 'hc': (24.80, 120.97, '新竹'), 'tp': (25.045, 121.53, '台北'), 'yl': (24.72, 121.76, '宜蘭'),
        'hl': (23.99, 121.60, '花蓮'), 'tt': (22.76, 121.14, '台東')}
AREA = {'ks': '高雄', 'tn': '台南', 'pts': '屏東', 'kt': '恆春墾丁', 'cy': '嘉義市', 'als': '阿里山', 'ch': '彰化・鹿港', 'tc': '台中', 'nt': '日月潭・清境',
        'hc': '新竹', 'tp': '台北・新北', 'yl': '宜蘭', 'hl': '花蓮', 'tt': '台東'}
KS_AREAS = ['鳳山', '苓雅', '新興', '前金', '前鎮', '三民', '鹽埕', '鼓山', '左營']
# 每次都找高雄；其他縣市每月輪流挑 3 個
KS_QUERIES = [('eat', '新開幕 餐廳'), ('izakaya', '新開 居酒屋'), ('bar', '新開 酒吧 調酒'), ('dessert', '新開 甜點 咖啡廳'),
              ('bbq', '新開 燒肉'), ('hotpot', '新開 火鍋'), ('snack', '新開 小吃'), ('massage', '新開 按摩 SPA'), ('hairspa', '越式洗髮 推薦'), ('ktv', '新開 KTV 歡唱')]
OTHER_QUERIES = [('eat', '新開幕 餐廳'), ('dessert', '新開 甜點 咖啡'), ('bar', '新開 酒吧'), ('sight', '新景點')]
BAD = re.compile(r'公關|陪酒|小吃部|女性|女子|限女|產後|月子|坐月子|伴唱|卡拉OK小吃|按摩院|理容')
PRICE = {'eat': 400, 'fine': 1500, 'snack': 120, 'bbq': 800, 'hotpot': 500, 'dessert': 220, 'izakaya': 700, 'bar': 600, 'massage': 1200, 'hairspa': 600, 'ktv': 500, 'sight': 0}
STAY = {'eat': 75, 'fine': 120, 'snack': 40, 'bbq': 100, 'hotpot': 90, 'dessert': 50, 'izakaya': 100, 'bar': 100, 'massage': 90, 'hairspa': 60, 'ktv': 120, 'sight': 75}

def load(n):
    with open(os.path.join(DATA, n), encoding='utf-8') as f: return json.load(f)
def save(n, o):
    with open(os.path.join(DATA, n), 'w', encoding='utf-8') as f: json.dump(o, f, ensure_ascii=False, indent=0)

def search(q, lat, lng, radius):
    body = json.dumps({'textQuery': q, 'languageCode': 'zh-TW', 'regionCode': 'TW', 'pageSize': 20,
                       'locationBias': {'circle': {'center': {'latitude': lat, 'longitude': lng}, 'radius': radius}}}).encode()
    req = urllib.request.Request('https://places.googleapis.com/v1/places:searchText', data=body, headers={
        'Content-Type': 'application/json', 'X-Goog-Api-Key': KEY,
        'X-Goog-FieldMask': 'places.id,places.displayName,places.location,places.rating,places.userRatingCount,places.regularOpeningHours,places.priceLevel,places.nationalPhoneNumber,places.types,places.formattedAddress,places.businessStatus'})
    with urllib.request.urlopen(req, timeout=30) as r: return json.loads(r.read()).get('places', [])

def hours(p):
    oh = p.get('regularOpeningHours') or {}
    per = oh.get('periods')
    if not per: return None
    res = [[] for _ in range(7)]
    for x in per:
        o = x.get('open', {}); c = x.get('close')
        d = (o.get('day', 0) + 6) % 7; s = o.get('hour', 0) * 60 + o.get('minute', 0)
        if not c: return [[[0, 1440]] for _ in range(7)]
        e = c.get('hour', 0) * 60 + c.get('minute', 0) + ((c.get('day', 0) - o.get('day', 0)) % 7) * 1440
        if e <= s: e += 1440
        res[d].append([s, e])
    return res

def km(a, b, c, d):
    return math.hypot((a - c) * 111, (b - d) * 102)

def main():
    meta = load('meta.json'); auto = meta.setdefault('auto', {})
    stamp = NOW.strftime('%Y-%m-%d %H:%M')
    if not KEY:
        auto['places'] = {'ok': False, 'at': stamp, 'msg': '還沒設定 Google 地圖金鑰（GOOGLE_MAPS_KEY），這次沒有找新店'}
        save('meta.json', meta); print(auto['places']); return
    places = load('places.json')
    have = {v.get('placeId') for v in places.values()} | {v.get('name') for v in places.values()}
    others = [k for k in HUBS if k != 'ks']
    pick = [others[(NOW.month * 3 + i) % len(others)] for i in range(3)]
    jobs = [('ks', c, '高雄 ' + q) for c, q in KS_QUERIES] + [(r, c, HUBS[r][2] + ' ' + q) for r in pick for c, q in OTHER_QUERIES]
    added, calls, errors = [], 0, []
    for reg, cat, q in jobs:
        lat, lng, _ = HUBS[reg]
        try: res = search(q, lat, lng, 15000 if reg == 'ks' else 20000); calls += 1
        except Exception as e: errors.append(str(e)[:80]); continue
        for p in res:
            name = (p.get('displayName') or {}).get('text', '')
            addr = p.get('formattedAddress', '')
            loc = p.get('location') or {}
            r, n = p.get('rating') or 0, p.get('userRatingCount') or 0
            if not name or p['id'] in have or name in have: continue
            if p.get('businessStatus', 'OPERATIONAL') != 'OPERATIONAL': continue
            if BAD.search(name): continue
            if n < 20 or n > 400: continue                      # 評論太少不準、太多就不是新店
            if r < (4.5 if cat in ('bar', 'massage', 'hairspa') else 4.3): continue
            if cat == 'massage' and re.search(r'越南|越式', name): continue   # 不收越南按摩店
            if cat == 'hairspa' and not re.search(r'洗髮|洗頭', name): continue
            if km(loc.get('latitude', 0), loc.get('longitude', 0), lat, lng) > (18 if reg == 'ks' else 30): continue
            if reg == 'ks' and not any(a in addr for a in KS_AREAS): continue
            hr = hours(p)
            if cat != 'sight' and not hr: continue
            pid = 'g_' + re.sub(r'[^A-Za-z0-9]', '', p['id'])[-12:]
            price = PRICE[cat]
            places[pid] = {'name': name, 'cat': cat, 'region': reg, 'area': AREA[reg], 'lat': round(loc['latitude'], 6), 'lng': round(loc['longitude'], 6),
                'rating': r, 'reviews': n, 'price': price, 'stay': STAY[cat], 'hours': hr or [[[0, 1440]] for _ in range(7)],
                'indoor': cat != 'sight', 'queue': False, 'park': '停車資訊未確認', 'ride': 'scooter' if reg == 'ks' else 'car', 'transit': '',
                'pros': '新店，Google 評價 %.1f（%d 則）' % (r, n), 'cons': '自動加入，評論還少，去之前先看一下評論',
                'flags': ['自動加入，尚未人工確認'], 'placeId': p['id'], 'checked': NOW.strftime('%Y-%m-%d'), 'source': 'Google 地圖',
                'isNew': True, 'addedBy': '每月自動找', 'phone': p.get('nationalPhoneNumber', ''), 'karaoke': cat == 'ktv',
                'priceRange': [price, round(price * 0.7), round(price * 1.5)] if price else [0, 0, 0]}
            have.add(p['id']); have.add(name); added.append('%s（%s，%.1f）' % (name, AREA[reg], r))
            if len(added) >= 30: break
    if added:
        save('places.json', places); meta['placesUpdated'] = NOW.strftime('%Y-%m-%d')
    msg = ('新增 %d 家：' % len(added) + '、'.join(added[:12]) + ('…' if len(added) > 12 else '')) if added else '這個月沒有符合條件的新店'
    if errors and not calls: auto['places'] = {'ok': False, 'at': stamp, 'msg': 'Google 地圖查詢失敗：' + errors[0]}
    else: auto['places'] = {'ok': True, 'at': stamp, 'msg': msg + '（查了 %d 次，這次輪到 %s）' % (calls, '、'.join(AREA[x] for x in pick))}
    save('meta.json', meta); print(auto['places'])

if __name__ == '__main__':
    main()
