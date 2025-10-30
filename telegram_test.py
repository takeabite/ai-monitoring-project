import asyncio
from telegram import Bot

async def main():
    bot = Bot(token="8241727073:AAGDxtB-nvX4axPCnGczOGBqo9xryO3GMdw")
    await bot.send_message(chat_id="5100081132", text="✅ 텔레그램 연결 테스트 성공!")

if __name__ == "__main__":
    asyncio.run(main())
