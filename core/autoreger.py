import asyncio
import random
import time
from asyncio import Semaphore, sleep, create_task, gather
from concurrent.futures import ThreadPoolExecutor

from core.utils import logger
from core.utils.file_to_list import file_to_list
from core.web3go import Web3Go

from inputs.config import (
    THREADS, CUSTOM_DELAY, KEYS_FILE_PATH, PROXIES_FILE_PATH
)


class AutoReger:
    def __init__(self):
        self.success = 0
        self.custom_user_delay = None

    @staticmethod
    def get_accounts():
        keys = file_to_list(KEYS_FILE_PATH)
        proxies = file_to_list(PROXIES_FILE_PATH)

        if not (min_accounts_len := len(keys)):
            logger.info(f"keys.txt is empty!")
            return

        accounts = []

        for i in range(min_accounts_len):
            accounts.append((
                keys[i],
                proxies[i] if len(proxies) > i else None
             ))

        return accounts

    async def start(self):
        self.custom_user_delay = CUSTOM_DELAY

        accounts = AutoReger.get_accounts()

        if accounts is None:
            return

        logger.info(f"Successfully grab {len(accounts)} accounts")

        semaphore = Semaphore(THREADS)

        tasks = []
        for account in accounts:
            task = create_task(self.worker(account, semaphore))
            tasks.append(task)

        await gather(* tasks)

        if self.success:
            logger.success(f"Successfully handled {self.success} accounts :)")
        else:
            logger.warning(f"No accounts handled :(")

    async def worker(self, account: tuple, semaphore: Semaphore):
        key, proxy = account
        logs = {"ok": False, "file": "fail.txt", "msg": ""}

        try:
            async with semaphore:
                await AutoReger.custom_delay()

                web3go = Web3Go(key, proxy)
                if await web3go.login():
                    await web3go.define_proxy(proxy)

                    logs["ok"] = await web3go.claim()

                    await web3go.logout()
        except Exception as e:
            logs["msg"] = str(e)
            logger.error(f"Error {e}")

        if logs["ok"]:
            logs["file"] = "success"
            logs["msg"] = "Claimed!"
            self.success += 1
        else:
            logs["msg"] = "Check logs/out.log for more info"

        web3go.logs(logs["file"], logs["msg"])

    @staticmethod
    async def custom_delay():
        if CUSTOM_DELAY[1] > 0:
            sleep_time = random.uniform(CUSTOM_DELAY[0], CUSTOM_DELAY[1])
            logger.info(f"Sleep for {int(sleep_time)} seconds")
            await sleep(sleep_time)

    @staticmethod
    def is_file_empty(path: str):
        return not open(path).read().strip()
