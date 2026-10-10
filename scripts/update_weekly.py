"""每週更新：中油油價、LINE TODAY 電影評分。只用 Python 標準函式庫，在 GitHub Actions 上跑。"""
import json, re, os, sys, html, datetime, urllib.request
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
TODAY = datetime.datetime.utcnow() + datetime.timedelta(hours=8)
UA = {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1',
      'Accept-Language': 'zh-TW,zh;q=0.9'}

def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8', 'replace')

def load(name):
    with open(os.path.join(DATA, name), encoding='utf-8') as f: return json.load(f)

def save(name, obj):
    with open(os.path.join(DATA, name), 'w', encoding='utf-8') as f: json.dump(obj, f, ensure_ascii=False, indent=1)

def fuel():
    x = get('https://vipmbr.cpc.com.tw/CPCSTN/ListPriceWebService.asmx/getCPCMainProdListPrice_XML')
    root = ET.fromstring(x)
    for t in root.iter():
        if t.tag.split('}')[-1] != 'Table': continue
        f = {c.tag.split('}')[-1]: (c.text or '').strip() for c in t}
        if f.get('產品名稱') == '95無鉛汽油':
            price = round(float(f['參考牌價_金額']), 1)
            d = f.get('牌價生效日期', '')
            start = datetime.date(int(d[:-4]) + 1911, int(d[-4:-2]), int(d[-2:])) if len(d) >= 7 else TODAY.date()
            end = start + datetime.timedelta(days=6)
            return {'price': price, 'type': '95 無鉛', 'week': start.isoformat() + '～' + end.strftime('%m-%d'), 'source': '台灣中油'}
    raise RuntimeError('找不到 95 無鉛')

def movies():
    """LINE TODAY 電影排行：抓頁面裡的 JSON 狀態，取片名、上映日、類型、片長、觀眾評分（10 分制）。"""
    pages = ['https://today.line.me/tw/v2/movie/chart/trending', 'https://today.line.me/tw/v2/movie/chart/inTheaters']
    found = {}
    debug = []
    for url in pages:
        try: h = get(url)
        except Exception as e: debug.append(url + ' ' + str(e)); continue
        debug.append(url + ' len=' + str(len(h)))
        # 1) 頁面內嵌的排行 JSON（items 陣列，每部有 movieId、rating.average、releaseDate、genres、runtime）
        try:
            idx = h.find('"movieId"')
            st = h.rfind('"items":[', 0, idx) + len('"items":')
            arr, _ = json.JSONDecoder().raw_decode(h, st)
            for it in arr:
                rt = it.get('rating') or {}
                if not it.get('title') or not rt.get('average'): continue
                rel = ''
                if it.get('releaseDate'): rel = datetime.datetime.utcfromtimestamp(int(it['releaseDate']) / 1000 + 8 * 3600).strftime('%Y-%m-%d')
                found.setdefault(it['title'].strip(), {'score': round(float(rt['average']), 1), 'count': rt.get('count'), 'release': rel,
                    'runtime': it.get('runtime'), 'genre': '、'.join(it.get('genres') or []), 'eng': it.get('engTitle', '')})
        except Exception as e:
            debug.append('json ' + str(e)[:80])
        if found: continue
        for m in re.finditer(r'\{[^{}]*?"title"\s*:\s*"([^"]{1,60})"[^{}]*?\}', h):
            blob = m.group(0)
            sc = re.search(r'"(?:score|rating|avgScore|averageScore|userScore)"\s*:\s*"?([0-9]+(?:\.[0-9]+)?)', blob)
            title = json.loads('"' + m.group(1) + '"') if '\\u' in m.group(1) else m.group(1)
            if not sc or not re.search(r'[一-鿿]', title): continue
            s = float(sc.group(1))
            if s > 10: s = s / 10
            rel = re.search(r'"(?:releaseDate|release|openDate|publishDate)"\s*:\s*"?(\d{4}[-/]\d{2}[-/]\d{2}|\d{10,13})', blob)
            run = re.search(r'"(?:runtime|duration|length)"\s*:\s*"?(\d{2,3})', blob)
            found.setdefault(title, {'score': s, 'release': rel.group(1) if rel else '', 'runtime': int(run.group(1)) if run else None})
        # 2) 退而求其次：純文字「片名 … 8.4」
        if not found:
            text = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', h, flags=re.S)
            text = html.unescape(re.sub(r'<[^>]+>', '\n', text))
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            for i, l in enumerate(lines):
                if re.fullmatch(r'\d\.\d', l) and i >= 2:
                    for back in range(1, 4):
                        t = lines[i - back]
                        if re.search(r'[一-鿿]', t) and len(t) <= 40 and not re.search(r'分鐘|上映|排行|統計', t):
                            found.setdefault(t, {'score': float(l), 'release': '', 'runtime': None}); break
    return found, debug

def main():
    meta = load('meta.json'); auto = meta.setdefault('auto', {}); changed = False
    try:
        f = fuel()
        if meta.get('fuel', {}).get('price') != f['price'] or meta.get('fuel', {}).get('week') != f['week']: changed = True
        meta['fuel'] = f; auto['fuel'] = {'ok': True, 'at': TODAY.strftime('%Y-%m-%d %H:%M'), 'msg': '95 無鉛 %.1f 元（%s）' % (f['price'], f['week'])}
    except Exception as e:
        auto['fuel'] = {'ok': False, 'at': TODAY.strftime('%Y-%m-%d %H:%M'), 'msg': '油價抓取失敗：' + str(e)[:120]}
    try:
        found, debug = movies()
        if os.environ.get('DP_DEBUG'):
            os.makedirs(os.path.join(ROOT, 'debug'), exist_ok=True)
            with open(os.path.join(ROOT, 'debug', 'line.txt'), 'w', encoding='utf-8') as fp:
                fp.write('\n'.join(debug) + '\n' + json.dumps(found, ensure_ascii=False, indent=1))
                try: fp.write('\n\n' + get('https://today.line.me/tw/v2/movie/chart/trending')[:400000])
                except Exception as e: fp.write(str(e))
        if len(found) < 3: raise RuntimeError('只抓到 %d 部，頁面格式可能改了' % len(found))
        mv = load('movies.json'); byTitle = {v['title']: k for k, v in mv.items()}
        today = TODAY.strftime('%Y-%m-%d'); n_new = 0
        for title, x in found.items():
            r5 = round(x['score'] / 2, 1)
            verdict = '觀眾評分很高' if x['score'] >= 8.8 else '評價不錯' if x['score'] >= 8 else '普通' if x['score'] >= 7 else '評價偏低'
            if x.get('count') is not None and x['count'] < 10: continue   # 評分人數太少先不算
            rel = x['release']
            if rel and rel.isdigit(): rel = datetime.datetime.utcfromtimestamp(int(rel[:10]) + 8 * 3600).strftime('%Y-%m-%d')
            rel = rel.replace('/', '-')
            k = byTitle.get(title)
            if k:
                if x.get('genre') and not mv[k].get('genre'): mv[k]['genre'] = x['genre']
                if x.get('runtime') and not mv[k].get('runtime'): mv[k]['runtime'] = x['runtime']
                mv[k].update({'rating': r5, 'ratingSrc': 'LINE TODAY 觀眾評分 %.1f/10' % x['score'] + ('（%d 人）' % x['count'] if x.get('count') else ''), 'verdict': verdict, 'checked': today})
                if rel and not mv[k].get('release'): mv[k]['release'] = rel
            else:
                n_new += 1; k = 'a' + TODAY.strftime('%y%m%d') + str(n_new)
                mv[k] = {'title': title, 'release': rel, 'genre': x.get('genre', ''), 'runtime': x['runtime'], 'rating': r5, 'ratingSrc': 'LINE TODAY 觀眾評分 %.1f/10' % x['score'] + ('（%d 人）' % x['count'] if x.get('count') else ''), 'summary': '', 'verdict': verdict, 'checked': today}
        # 上映超過 8 週、這次又沒出現在排行的，當作下檔
        cut = (TODAY - datetime.timedelta(days=56)).strftime('%Y-%m-%d')
        for k in [k for k, v in mv.items() if v['title'] not in found and v.get('release') and v['release'] < cut]: mv.pop(k)
        save('movies.json', mv); changed = True
        auto['movies'] = {'ok': True, 'at': TODAY.strftime('%Y-%m-%d %H:%M'), 'msg': '更新 %d 部、新增 %d 部' % (len(found), n_new)}
    except Exception as e:
        auto['movies'] = {'ok': False, 'at': TODAY.strftime('%Y-%m-%d %H:%M'), 'msg': '電影抓取失敗：' + str(e)[:120]}
    save('meta.json', meta)
    print(json.dumps(auto, ensure_ascii=False, indent=1))

if __name__ == '__main__':
    main()
