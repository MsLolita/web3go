import asyncio
import ctypes
import os

from core.autoreger import AutoReger
from art import tprint


def bot_info(name: str = ""):
    tprint(name)

    if os.name == 'nt':
        ctypes.windll.kernel32.SetConsoleTitleW(f"{name}")
    print("EnJoYeR's <crypto/> moves: https://t.me/+tdC-PXRzhnczNDli\n")


async def main():
    bot_info("Web3Go_Daily")
    await AutoReger().start()


if __name__ == '__main__':
    asyncio.run(main())
