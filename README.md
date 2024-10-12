# notion-asset-aws-lambda
Python code on AWS Lambda that fetches stock price data from various sources and returns the summary. Output destination depends on the input source, supports both from LINE bot (Messaging API) and a plain HTTP request.

## Runtime Configurations
Python 3.12 x86_64

## Usage Limitations
Since this function fetches data from various public (but enterprise) sources, only non-frequent private use is strongly expected.

## Data Source
Needs to be set in `urls.py` for cryptos, gold, indices and stocks.

```python
async def fetchCrypto(session: aiohttp.ClientSession, product_code:str) -> float|None:
    return None

async def fetchGold(session: aiohttp.ClientSession) -> float|None:
    return None

async def fetchIndex(session: aiohttp.ClientSession, fund_id_arr:str) -> float|None:
    return None

async def fetchStock(session: aiohttp.ClientSession, codes:str) -> float|None:
    return None
```

## Modules and Layers
Layer is dynamically created on `terraform apply`. Module installation is done by `pip_init.sh`.
| Name      | Comments |
|-----------|----------|
| aiohttp   | For async http requests |

## Enironmental values required
Define these in `config.json`.
- `LINE_CHANNEL_ACCESS_TOKEN` & `LINE_CHANNEL_SECRET` & `LINE_USER_ID`: Channel Access Token, Channel Secret and your User ID for LINE Messaging API. All of them are available in LINE Developer Console.
- `EVENT_PWD`: User Password to be used to check when the function URL is triggered (plain HTTP request)
- `EVENT_USER`: User Id to be used to check when the function URL gets triggered (plain HTTP request)

## How to use
- Trigger(POST) the function URL with headers with EVENT_PWD and EVENT_USER as password and user respectively.
- Set the function URL to LINE Webhook URL of your LINE bot so that you can get the result through LINE.