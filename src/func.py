import json
import datetime
import os
import base64
import asyncio
import aiohttp
import hmac
import hashlib


def authorize(x_line_signature, body_str:str):
    channel_secret = os.getenv('LINE_CHANNEL_SECRET')
    hash = hmac.new(channel_secret.encode('utf-8'), body_str.encode('utf-8'), hashlib.sha256).digest()
    signature = base64.b64encode(hash).decode('utf-8')
    return x_line_signature == signature

async def getRequest(session: aiohttp.ClientSession, url: str):
    return await session.get(url)

async def postRequest(session: aiohttp.ClientSession, url: str):
    return await session.post(url)

def getAllProperties():
    # with open("./assets.json", mode="r", encoding="utf-8") as f:
    #     data = json.load(f)
    assets_data = os.getenv('ASSETS_DATA')
    assert assets_data
    data = json.loads(assets_data)
    assert 'assets' in data
    return data

async def fetchBitFlyer(session: aiohttp.ClientSession, code: str):
    raw_resp: aiohttp.ClientResponse = await getRequest(session, os.environ['PREFIX_CRYPTO']+code)
    if raw_resp.status != 200:
        return None
    else:
        resp = await raw_resp.json()
        return float(resp['ltp'])

async def fetchMinkabuFund(session: aiohttp.ClientSession, code: str):
    raw_resp: aiohttp.ClientResponse = await getRequest(session, os.environ['PREFIX_INDEX']+code)
    if raw_resp.status != 200:
        return None
    else:
        resp = await raw_resp.json()
        return float(resp['fund_data'][0]['fund_price'])

async def fetchMinkabuStock(session: aiohttp.ClientSession, code: str):
    raw_resp: aiohttp.ClientResponse = await getRequest(session, os.environ['PREFIX_STOCK']+code)
    if raw_resp.status != 200:
        return None
    else:
        resp = await raw_resp.json()
        return float(resp['items'][0]['price'])

async def fetchSbiGold(session: aiohttp.ClientSession):
    raw_resp: aiohttp.ClientResponse = await postRequest(session, os.environ['PREFIX_GOLD'])
    if raw_resp.status != 200:
        return None
    else:
        resp = json.loads(json.loads(await raw_resp.text())['data'])
        return float(resp['FGNOK']['BID']['px'])

async def processAsset(session: aiohttp.ClientSession, asset: dict[str, str]):
    price = None
    if asset['datasrc'] == 'BITFLYER':
        price = await fetchBitFlyer(session, asset['code'])
    elif asset['datasrc'] == 'MINKABU_FUND':
        price = await fetchMinkabuFund(session, asset['code'])
    elif asset['datasrc'] == 'MINKABU_STOCK':
        price = await fetchMinkabuStock(session, asset['code'])
    elif asset['datasrc'] == 'SBI_GOLD':
        price = await fetchSbiGold(session)
    return asset['name'], price

async def process(line_user_id=None):
    async with aiohttp.ClientSession() as session:
        if line_user_id:
            channel_access_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
            headers = {
                'content-type': 'application/json',
                'Authorization': f"Bearer {channel_access_token}"
            }
            payload = {
                "to": line_user_id,
                "messages": [{"type": "text", "text": "確認中..."}]
            }
            await session.post('https://api.line.me/v2/bot/message/push', headers=headers, data=json.dumps(payload))

        props = getAllProperties()
        coroutines = [processAsset(session, asset) for asset in props['assets']]
        for asset in props['assets']:
            coroutines.append(processAsset(session, asset))
            
        prices = {name:price for name, price in await asyncio.gather(*coroutines)} 
        
        sum_purchased = 0
        sum_jika = 0
        sum_soneki = 0
        asset_price = []
        for asset in props['assets']:
            assert asset['name'] in prices
            if not prices[asset['name']]:
                current_price = None
                gain = 0
            else:
                current_price = float(asset["lot"])*prices[asset['name']]
                gain = current_price - asset["purchased"]

            sum_purchased += asset["purchased"]
            sum_jika += current_price
            sum_soneki += gain
            if line_user_id:
                asset_price.append((asset, current_price))

        if line_user_id:
            channel_access_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
            headers = {
                'content-type': 'application/json',
                'Authorization': f"Bearer {channel_access_token}"
            }
            sorted_asset_price = list(sorted(asset_price, key=lambda x: x[0]["datasrc"]))
            sorted_asset_price.append(({"name": "総計", "purchased": sum_purchased}, sum_jika))
            payload = {
                "to": line_user_id,
                "messages": [line_flex_message(sorted_asset_price)]
            }
            await session.post('https://api.line.me/v2/bot/message/push', headers=headers, data=json.dumps(payload))
            return None
        else:
            return (sum_jika, sum_soneki)
    
def line_flex_message_vbox(contents, opt=None):
    base = {
        "type": "box",
        "layout": "vertical",
        "contents": contents
    }
    base.update(opt or {})
    return base

def line_flex_message_bbox(contents, opt=None):
    base = {
        "type": "box",
        "layout": "baseline",
        "contents": contents
    }
    base.update(opt or {})
    return base

def line_flex_message_text(text:str, color:str="#000000", size:str="sm", opt=None):
    base = {
        "type": "text",
        "text": text,
        "color": color,
        "size": size,
    }
    base.update(opt or {})
    return base

def line_flex_message(asset_price: list[tuple[dict, float]]):
    return {
        "type": "flex",
        "altText": "This is a Flex Message",
        "contents": {
            "type": "bubble",
            "body": line_flex_message_vbox([
                        line_flex_message_bbox([
                            line_flex_message_text("時価", color="#aaaaaa",size="sm", opt={"align": "end", "flex": 5}),
                            line_flex_message_text("損益", color="#aaaaaa",size="sm", opt={"align": "end", "flex": 6}),
                            line_flex_message_text("損益率", color="#aaaaaa",size="sm", opt={"align": "end", "flex": 4}),
                        ]),
                        line_flex_message_vbox([
                            line_flex_message_vbox([
                                line_flex_message_text(asset['name'], size="sm", opt={"weight": "bold", "wrap": True}),
                                line_flex_message_bbox([
                                    line_flex_message_text(f"{int(current_price):,}円" if current_price else "エラー", color="#666666", size="sm", opt={"align": "end", "flex": 5}),
                                    line_flex_message_text(f"{int(current_price-asset['purchased']):+,}円" if current_price else "エラー", color="#02D46A" if current_price and current_price > asset['purchased'] else "#F63428", size="sm", opt={"align": "end", "flex": 6}),
                                    line_flex_message_text(f"{(current_price-asset['purchased'])/asset['purchased']*100:+,.2f}%" if current_price else "エラー", color="#02D46A" if current_price and current_price > asset['purchased'] else "#F63428", size="sm", opt={"align": "end", "flex": 4})
                                ]),
                            ], opt={"margin": "0px"})
                            for asset, current_price in asset_price ], opt={"margin": "0px"})
                        ], opt={"spacing": "16px"}
                    )
        }
    }

def lambda_handler(event, context):
    if not "content-type" in event["headers"] or not str(event["headers"]["content-type"]).startswith("application/json"):
        return {
            'statusCode': 400,
            'message': f"Bad Request"
        }
    line_reply_token = None
    body = json.loads(event["body"])
    
    if 'x-line-signature' in event['headers']:
        x_line_signature = event['headers'].get('x-line-signature')
        if not authorize(x_line_signature, str(event["body"])):
            return {
                'statusCode': 400,
                'message': f"Bad Request"
            }
        event_data = body['events'][0]
        message = event_data['message']['text']
        if message != "確認":
            return {
                'statusCode': 200
            }
        line_user_id = os.getenv("LINE_USER_ID")
    elif not 'user' in body or not 'password' in body:
        return {
            'statusCode': 401,
            'message': f"Unauthenticated"
        }
    elif body['user'] != os.environ['EVENT_USER'] or body['password'] != os.environ['EVENT_PWD']:
        return { 'statusCode': 401,  'message': f"user: {body['user']}, password: {body['password']}"}
    

    sums = asyncio.run(process(line_user_id))
    return {
        'statusCode': 200,
        'body': f"資産 [{datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).strftime('%y/%m/%d %H:%M:%S')}]\n{sums[0]:+,.2f} ({sums[1]:+,.2f})" if sums else "sent successfully"
    }

# print(lambda_handler({"headers":{"content-type": "application/json"}, "body":json.dumps({"user": "a", "password":"b"})}, None))
