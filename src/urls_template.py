import aiohttp

async def fetchCrypto(session: aiohttp.ClientSession, product_code:str) -> float|None:
    return None

async def fetchGold(session: aiohttp.ClientSession) -> float|None:
    return None

async def fetchIndex(session: aiohttp.ClientSession, fund_id_arr:str) -> float|None:
    return None

async def fetchStock(session: aiohttp.ClientSession, codes:str) -> float|None:
    return None
