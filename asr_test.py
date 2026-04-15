import asyncio
import aiohttp

async def test_request(session, i):
    async with session.post("http://localhost:8005/api/v1/asr/streaming") as resp:
        result = await resp.json()
        print(f"Request {i}: {result}")
        return result

async def main():
    async with aiohttp.ClientSession() as session:
        tasks = [test_request(session, i) for i in range(9)]
        results = await asyncio.gather(*tasks)
        print(f"All {len(results)} requests completed")

asyncio.run(main())