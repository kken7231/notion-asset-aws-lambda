import json
import datetime
import os
from io import BytesIO
import base64
from functools import reduce
import asyncio
import aiohttp

from reportlab.platypus import BaseDocTemplate, PageTemplate
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import Paragraph, Table, TableStyle
from reportlab.platypus.flowables import Spacer
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4, portrait, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus.frames import Frame

propframes = {
    '名前': 'title/0/plain_text', 
    'タグ': 'select/name',
    'code': 'rich_text/0/plain_text',
    'data_src': 'select/name',
    '時価': 'formula/number',
    '損益': 'formula/number',
    '購入価格': 'number'
}

async def getRequest(session: aiohttp.ClientSession, url: str):
    return await session.get(url)

async def postRequest(session: aiohttp.ClientSession, url: str):
    return await session.post(url)

async def patchRequest(session: aiohttp.ClientSession, url: str, data=None):
    return await session.patch(url, data=data)

async def notionPatch(session: aiohttp.ClientSession, url: str, data=None):
    return await session.patch(url, data=data, headers={'Authorization': f"Bearer {os.environ['API_KEY']}", 'Notion-Version': '2022-06-28', 'Content-Type': 'application/json'})

async def notionDbQuery(session: aiohttp.ClientSession, database_id: str):
    return await session.post(f"https://api.notion.com/v1/databases/{database_id}/query", headers={'Authorization': f"Bearer {os.environ['API_KEY']}", 'Notion-Version': '2022-06-28', 'Content-Type': 'application/json'})

def getProperties(page: dict[str, str]):
    assert 'id' in list(page.keys())
    retVal = {}
    retVal['id'] = page['id']
    assert 'properties' in list(page.keys())
    props = page['properties']
    for pkey, ploc in propframes.items():
        if not pkey in list(props.keys()):
            print(f"{pkey} not in the keys")
            assert True
        obj = props[pkey]
        locs = ploc.split('/')
        for loc in locs:
            index = loc
            if loc.isnumeric():
                index = int(loc)
            else:
                assert index in list(obj.keys())
            obj = obj[index]
        retVal[pkey] = obj
    return retVal

async def fetchBitFlyer(session: aiohttp.ClientSession, code: str):
    raw_resp: aiohttp.ClientResponse = await getRequest(session, os.environ['PREFIX_CRYPTO']+code)
    if raw_resp.status != 200:
        return -1
    else:
        resp = await raw_resp.json()
        return float(resp['ltp'])

async def fetchMinkabuFund(session: aiohttp.ClientSession, code: str):
    raw_resp: aiohttp.ClientResponse = await getRequest(session, os.environ['PREFIX_INDEX']+code)
    if raw_resp.status != 200:
        return -1
    else:
        resp = await raw_resp.json()
        return float(resp['fund_data'][0]['fund_price'])

async def fetchMinkabuStock(session: aiohttp.ClientSession, code: str):
    raw_resp: aiohttp.ClientResponse = await getRequest(session, os.environ['PREFIX_STOCK']+code)
    if raw_resp.status != 200:
        return -1
    else:
        resp = await raw_resp.json()
        return float(resp['items'][0]['price'])

async def fetchSbiGold(session: aiohttp.ClientSession):
    raw_resp: aiohttp.ClientResponse = await postRequest(session, os.environ['PREFIX_GOLD'])
    if raw_resp.status != 200:
        return -1
    else:
        resp = json.loads(json.loads(await raw_resp.text())['data'])
        return float(resp['FGNOK']['BID']['px'])

async def processAsset(session: aiohttp.ClientSession, props: dict[str, str]):
    price = -1
    if props['data_src'] == 'BITFLYER':
        price = await fetchBitFlyer(session, props['code'])
    elif props['data_src'] == 'MINKABU_FUND':
        price = await fetchMinkabuFund(session, props['code'])
    elif props['data_src'] == 'MINKABU_STOCK':
        price = await fetchMinkabuStock(session, props['code'])
    elif props['data_src'] == 'SBI_GOLD':
        price = await fetchSbiGold(session)

    if price == -1:
        await notionPatch(session, f"https://api.notion.com/v1/pages/{props['id']}", setStatus("異常"))
        print(f"Error on fetching {props['名前']}: {await raw_resp.text()}")
        return

    raw_resp = await notionPatch(session, f"https://api.notion.com/v1/pages/{props['id']}", '{"properties":{"単価":{"number":'+str(price)+'}}}')
    if raw_resp.status != 200:
        await notionPatch(session, f"https://api.notion.com/v1/pages/{props['id']}", setStatus("異常"))
        print(f"Error on {props['名前']}: {await raw_resp.text()}")
    else:
        await notionPatch(session, f"https://api.notion.com/v1/pages/{props['id']}", setStatus("正常"))
        print(f"{props['名前']} done.")

def setStatus(status: str):
    return ('{"properties":{"エラー":{"select":{"name":"'+status+'"}}}}').encode('utf-8')

def reportPDF(values):
    pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))

    buf = BytesIO()
    doc = BaseDocTemplate(buf, title="asset-report", pagesize=portrait(A4))

    frames = [
            Frame(0, A4[1]-40*mm, A4[0], 20*mm, showBoundary=0),
            Frame(15*mm, 20*mm, A4[0]-30*mm, A4[1]-60*mm, showBoundary=0),
        ]

    page_template = PageTemplate("frames", frames=frames)
    doc.addPageTemplates(page_template)

    style_dict_title ={
        "name": "title",
        "fontSize":24,
        "alignment": TA_CENTER
        }
    style_title = ParagraphStyle(**style_dict_title)
    style_dict_subtitle ={
        "name": "subtitle",
        "fontSize":18,
        "alignment": TA_LEFT
        }
    style_subtitle = ParagraphStyle(**style_dict_subtitle)
    style_dict_body ={
        "name": "body",
        "fontSize":11,
        "alignment": TA_LEFT
        }
    style_body = ParagraphStyle(**style_dict_body)
    flowables = []

    space = Spacer(10*mm, 10*mm)

    para = Paragraph(f"Assets Report - {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).strftime('%y/%m/%d %H:%M')}", style_title)
    flowables.append(para)
    flowables.append(space)

    data = [['Name', 'Purchased', 'Current', 'Gain', '']]
    data.extend([[v['name'], f"{v['purchased']:,.2f}", f"{v['current']:,.2f}", f"{v['gain']:+,.2f}", f"{v['gain_p']:+.2f}%"] for v in sorted(values, key=lambda x: x['gain'], reverse=True)])
    sum = reduce(lambda a, b: 
        {"purchased": a['purchased'], "current": a['current'], "gain": a['gain']} if b is None 
        else {"purchased": (a['purchased']+b['purchased']), "current": (a['current']+b['current']), "gain": (a['gain']+b['gain'])}, values)
    data.append(['Summary', f"{sum['purchased']:,.2f}", f"{sum['current']:,.2f}", f"{sum['gain']:+,.2f}", f"{sum['gain']/sum['purchased']*100:+.2f}%"])
    t = Table(data)
    t.setStyle(TableStyle([
        ('FONT', (0,0), (-1,-1), 'HeiseiKakuGo-W5', 10),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ROWBACKGROUNDS', (0, 0), (-1, 0), [colors.black]),
        ('SPAN',(-2,0),(-1,0)),
        ('ALIGNMENT', (1, 0), (-1, 0), 'CENTER'),
        ('ALIGNMENT', (1, 1), (-1, -1), 'RIGHT'),
        ('INNERGRID', (0,0), (-1,-1), 0.25, colors.black),
        ('BOX', (0,0), (-1,-1), 0.25, colors.black),
        ('LINEABOVE',(0,-1),(-1, -1),1.5,colors.black),
    ]))
    flowables.append(t)
    flowables.append(space)

    data = [['Name', 'Purchased', 'Current', 'Gain', '']]
    tags = set(map(lambda v: v['tag'], values))
    reduced = {}
    for t in tags:
        reduced[t] = {'name': t, 'purchased': 0, 'current': 0, 'gain': 0}
    for v in values:
        for k in ['purchased', 'current', 'gain']:
            reduced[v['tag']][k] += v[k]
    data.extend([[v['name'], f"{v['purchased']:,.2f}", f"{v['current']:,.2f}", f"{v['gain']:+,.2f}", f"{v['gain']/v['purchased']*100:+.2f}%"] for v in sorted(reduced.values(), key=lambda x: x['name'])])
    data.append(['Summary', f"{sum['purchased']:,.2f}", f"{sum['current']:,.2f}", f"{sum['gain']:+,.2f}", f"{sum['gain']/sum['purchased']*100:+.2f}%"])
    t = Table(data)
    t.setStyle(TableStyle([
        ('FONT', (0,0), (-1,-1), 'HeiseiKakuGo-W5', 10),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ROWBACKGROUNDS', (0, 0), (-1, 0), [colors.black]),
        ('SPAN',(-2,0),(-1,0)),
        ('ALIGNMENT', (1, 0), (-1, 0), 'CENTER'),
        ('ALIGNMENT', (1, 1), (-1, -1), 'RIGHT'),
        ('INNERGRID', (0,0), (-1,-1), 0.25, colors.black),
        ('BOX', (0,0), (-1,-1), 0.25, colors.black),
        ('LINEABOVE',(0,-1),(-1, -1),1.5,colors.black),
    ]))
    flowables.append(t)

    doc.multiBuild(flowables)
    return base64.b64encode(buf.getbuffer()).decode()

async def process():
    async with aiohttp.ClientSession() as session:
        await notionPatch(session, f"https://api.notion.com/v1/databases/{os.environ['DATABASE_ID']}/", '{"title":[{"text":{"content": "資産 [更新中]"}}]}')

        resp = await notionDbQuery(session, os.environ["DATABASE_ID"])
        results = json.loads(await resp.text())['results']
        await asyncio.gather(*[notionPatch(session, f"https://api.notion.com/v1/pages/{res['id']}", setStatus("更新中")) for res in results])
        coroutines = []
        for res in results:
            props = getProperties(res)
            coroutines.append(processAsset(session, props))
        await asyncio.gather(*coroutines)
        await notionPatch(session, f"https://api.notion.com/v1/databases/{os.environ['DATABASE_ID']}/", '{"title":[{"text":{"content": "資産 ['+datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).strftime("%y/%m/%d %H:%M:%S")+']"}}]}')

        resp = await notionDbQuery(session, os.environ["DATABASE_ID"])
        results = json.loads(await resp.text())['results']
        sum_jika = 0
        sum_soneki = 0
        values = []
        for res in results:
            props = getProperties(res)
            values.append({
                'name': props['名前'],
                'tag': props['タグ'],
                'purchased': float(props['購入価格']),
                'current': float(props['時価']),
                'gain': float(props['損益']),
                'gain_p': float(props['損益'])/float(props['購入価格'])*100,
            })
            sum_jika += float(props['時価'])
            sum_soneki += float(props['損益'])
        return (reportPDF(values), (sum_jika, sum_soneki))

def lambda_handler(event, context):
    data = json.loads(event["body"])
    if not 'user' in list(data.keys()) or not 'password' in list(data.keys()):
        return { 'statusCode': 400}
    elif data['user'] != os.environ['EVENT_USER'] or data['password'] != os.environ['EVENT_PWD']:
        return { 'statusCode': 401,  'body': f"user: {data['user']}, password: {data['password']}"}
    else:
        rep, sums = asyncio.run(process())
        return {
            'statusCode': 200,
            'body': f"資産 [{datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).strftime('%y/%m/%d %H:%M:%S')}]\n{sums[0]:+,.2f} ({sums[1]:+,.2f})\n{rep}"
        }