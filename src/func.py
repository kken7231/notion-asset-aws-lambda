import json
import datetime
import os
import base64
import asyncio
import aiohttp
import hmac
import hashlib
import urls

def authorize(x_line_signature, body_str:str):
    channel_secret = os.getenv('LINE_CHANNEL_SECRET')
    hash = hmac.new(channel_secret.encode('utf-8'), body_str.encode('utf-8'), hashlib.sha256).digest()
    signature = base64.b64encode(hash).decode('utf-8')
    return x_line_signature == signature

def getAllProperties():
    assets_data = os.getenv('ASSETS_DATA')
    assert assets_data
    data = json.loads(assets_data)
    assert 'assets' in data
    return data

async def processAsset(session: aiohttp.ClientSession, asset: dict[str, str]):
    price = None
    if not 'type' in asset:
        price = None
    elif asset['type'] == 'crypto':
        price = await urls.fetchCrypto(session, asset['code'])
    elif asset['type'] == 'index':
        price = await urls.fetchIndex(session, asset['code'])
    elif asset['type'] == 'stock':
        price = await urls.fetchStock(session, asset['code'])
    elif asset['type'] == 'gold':
        price = await urls.fetchGold(session)
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
        sum_curprice = 0
        sum_gain = 0
        has_error = False
        line_content = []
        def get_font_color(is_green: bool):
            return "#02D46A" if is_green else "#F63428"
        
        for asset in list(sorted(props['assets'], key=lambda x: x["datasrc"])):
            assert asset['name'] in prices
            if not prices[asset['name']]:
                # no data
                current_price = None
                gain = 0
                has_error = True
            else:
                current_price = float(asset["lot"])*prices[asset['name']]
                gain = current_price - asset["purchased"]

            sum_purchased += asset["purchased"]
            sum_curprice += current_price
            sum_gain += gain
            if line_user_id:
                line_content.append(
                    line_flex_message_vbox([
                        line_flex_message_text(asset['name'], opt={"weight": "bold", "wrap": True}),
                        line_flex_message_bbox([
                            line_flex_message_text(
                                f"{int(current_price):,}円" if current_price else "-", 
                                color="#666666", 
                                opt={"align": "end", "flex": 5}),
                            line_flex_message_text(
                                f"{int(current_price-asset['purchased']):+,}円" if current_price else "-", 
                                color=get_font_color(current_price and current_price > asset['purchased']), 
                                opt={"align": "end", "flex": 6}),
                            line_flex_message_text(
                                f"{(current_price-asset['purchased'])/asset['purchased']*100:+,.1f}%" if current_price else "-", 
                                color=get_font_color(current_price and current_price > asset['purchased']),
                                opt={"align": "end", "flex": 4})
                        ]),
                    ], opt={"margin": "8px"})
                )
                

        if line_user_id:
            channel_access_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
            headers = {
                'content-type': 'application/json',
                'Authorization': f"Bearer {channel_access_token}"
            }
            line_content.append(
                line_flex_message_vbox([
                    {"type": "separator","margin": "8px"},
                    line_flex_message_bbox([
                        line_flex_message_text(
                            f"{int(sum_curprice):,}円" if current_price else "-", 
                            color="#000000", 
                            opt={"weight": "bold", "align": "end", "flex": 5}),
                        line_flex_message_text(
                            f"{int(sum_curprice-sum_purchased):+,}円" if not has_error else "-", 
                            color=get_font_color(not has_error and sum_curprice > sum_purchased), 
                            opt={"weight": "bold", "align": "end", "flex": 6}),
                        line_flex_message_text(
                            f"{(sum_curprice-sum_purchased)/sum_purchased*100:+,.1f}%" if not has_error else "-", 
                            color=get_font_color(not has_error and sum_curprice > sum_purchased),
                            opt={"weight": "bold", "align": "end", "flex": 4})
                    ], opt={"margin": "8px"}),
                ])
            )
            payload = {
                "to": line_user_id,
                "messages": [line_flex_message(line_content)]
            }
            await session.post('https://api.line.me/v2/bot/message/push', headers=headers, data=json.dumps(payload))
            return None
        else:
            return (sum_curprice, sum_gain)
    
def line_flex_message_vbox(contents, opt=None):
    base = {"type": "box", "layout": "vertical", "contents": contents}
    base.update(opt or {})
    return base

def line_flex_message_bbox(contents, opt=None):
    base = {"type": "box", "layout": "baseline", "contents": contents}
    base.update(opt or {})
    return base

def line_flex_message_text(text:str, color:str="#000000", size:str="sm", opt=None):
    base = {"type": "text", "text": text, "color": color, "size": size}
    base.update(opt or {})
    return base

def line_flex_message(line_content: list[dict[str]]):
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
                        line_flex_message_vbox(line_content)
                    ])
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
