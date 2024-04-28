import asyncio
import datetime
import json
import random

import aiohttp
from aiohttp_socks import ProxyType, ProxyConnector, ChainProxyConnector
from tenacity import retry, stop_after_attempt, stop_after_delay
from web3 import Web3
from web3.exceptions import TimeExhausted

from inputs import config
from inputs.config import MOBILE_PROXY_CHANGE_IP_LINK, MOBILE_PROXY
from .utils import Web3Utils, logger
from .utils.file_manager import str_to_file


class Web3Go:
    def __init__(self, key: str, proxy: str = None):
        self.web3_utils = Web3Utils(key=key)
        # self.proxy = f'http://{proxy}' if proxy else None

        self.headers = {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'uk-UA,uk;q=0.9',
            'Connection': 'keep-alive',
            'Origin': 'https://reiki.web3go.xyz',
            'Referer': 'https://reiki.web3go.xyz/taskboard',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'X-App-Channel': 'DIN',
            'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
        }

        self.session = None
        self.proxy = proxy

    async def define_proxy(self, proxy: str):
        if MOBILE_PROXY:
            await Web3Go.change_ip()
            self.proxy = MOBILE_PROXY

        if proxy is not None:
            self.proxy = proxy

        connector = self.proxy and ProxyConnector.from_url(f'http://{self.proxy}')
        self.session = aiohttp.ClientSession(
            headers=self.headers,
            trust_env=True,
            connector=connector
        )

    @staticmethod
    async def change_ip():
        async with aiohttp.ClientSession() as session:
            await session.get(MOBILE_PROXY_CHANGE_IP_LINK)

    @retry(stop=stop_after_attempt(20))
    async def login(self):
        url = 'https://reiki.web3go.xyz/api/account/web3/web3_challenge'
        params = await self.get_login_params()
        address = params["address"]
        nonce = params["nonce"]
        msg = f"reiki.web3go.xyz wants you to sign in with your Ethereum account:\n{address}\n\n{params['challenge']}\n\nURI: https://reiki.web3go.xyz\nVersion: 1\nChain ID: 56\nNonce: {nonce}\nIssued At: {Web3Go.get_utc_timestamp()}"

        json_data = {
            'address': address,
            'nonce': nonce,
            'challenge': '{"msg":"' + msg.replace('\n', '\\n') + '"}',
            'signature': self.web3_utils.get_signed_code(msg),
        }

        response = await self.session.post(url, json=json_data)

        res_json = await response.json()
        auth_token = res_json.get("extra", {}).get("token")

        if auth_token:
            self.upd_login_token(auth_token)

        return bool(auth_token)

    @retry(stop=stop_after_attempt(20))
    async def get_login_params(self):
        url = 'https://reiki.web3go.xyz/api/account/web3/web3_nonce'

        json_data = {
            'address': self.web3_utils.acct.address,
        }

        response = await self.session.post(url, json=json_data, ssl=False)

        return await response.json()

    def upd_login_token(self, token: str):
        self.session.headers["Authorization"] = f"Bearer {token}"

    @retry(stop=stop_after_attempt(20))
    async def claim(self):
        url = 'https://reiki.web3go.xyz/api/checkin'

        params = {
            'day': self.get_current_date(),
        }

        response = await self.session.put(url, params=params)

        assert await response.text() == "true"
        return True

    async def roll_up_lottery(self, lottery_step: int = 2000):
        leafs = await self.get_leaf_amount()

        if leafs < lottery_step:
            logger.info(f"{self.web3_utils} | Not enough leafs to spin: {leafs} leafs")
            return

        while leafs >= lottery_step:
            await asyncio.sleep(random.uniform(3, 5))
            prize = await self.spin_lottery()
            leafs -= lottery_step
            logger.info(f"{self.web3_utils} | Prize: {prize} | Leafs left: {leafs}")

    @retry(stop=stop_after_attempt(5))
    async def get_lottery_result(self):
        url = 'https://reiki.web3go.xyz/api/lottery/offchain'

        response = await self.session.get(url)

        return await response.json()

    async def get_leaf_amount(self):
        resp_json = await self.get_lottery_result()
        return resp_json["userGoldLeafCount"]

    @retry(stop=stop_after_attempt(5))
    async def spin_lottery(self):
        url = "https://reiki.web3go.xyz/api/lottery/try"

        response = await self.session.post(url)
        resp_json = await response.json()

        return resp_json["prize"]

    async def logout(self):
        await self.session.close()

    @staticmethod
    def get_current_date():
        return datetime.datetime.now().strftime("%Y-%m-%d")

    @staticmethod
    def get_utc_timestamp():
        return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    def logs(self, file_name: str, msg_result: str = ""):
        address = self.web3_utils.acct.address
        file_msg = f"{address}|{self.proxy}"
        str_to_file(f"./logs/{file_name}.txt", file_msg)
        msg_result = msg_result and " | " + str(msg_result)

        if file_name == "success":
            logger.success(f"{address}{msg_result}")
        else:
            logger.error(f"{address}{msg_result}")

    @retry(stop=stop_after_attempt(5))
    async def get_minted_balance(self):
        response = await self.session.get("https://reiki.web3go.xyz/api/lottery/mint/info", proxy=self.proxy)
        json_data = await response.json()
        minted_chip = json_data.get("mintedChip")
        minted_piece = json_data.get("mintedPiece")
        wafer = json_data.get("wafer")
        logger.info(
            f"Key: ...{self.web3_utils.acct.key.hex()[30:]} | minted balance: chip: {minted_chip}, piece: {minted_piece}, wafer: {wafer}")
        return minted_chip, minted_piece

    @retry(stop=stop_after_attempt(5))
    async def get_lottery_balance(self, print:bool):
        response = await self.session.get("https://reiki.web3go.xyz/api/lottery/offchain", proxy=self.proxy)
        json_data = await response.json()
        leaves = json_data.get("userGoldLeafCount")
        chip = json_data.get("chipNum")
        piece = json_data.get("pieceNum")
        if print:
            logger.info(f"Key: ...{self.web3_utils.acct.key.hex()[30:]} | Balance: leaves: {leaves}, chip: {chip}, piece: {piece}")
        return leaves, chip, piece


    async def mint_chip_and_pieces(self):
        try:
            leaves_balance, unminted_chip, unminted_piece = await self.get_lottery_balance(print=False)
            logger.info(f"Key: ...{self.web3_utils.acct.key.hex()[30:]} | unminted_chip = {unminted_chip}, unminted_piece = {unminted_piece}")
            minted_chip, minted_piece = await self.get_minted_balance()
            if unminted_chip > 0:
                chip_amount_to_mint = unminted_chip
                logger.info(f"Key: ...{self.web3_utils.acct.key.hex()[30:]} | need to mint {chip_amount_to_mint} chips")
                await self.mint(chip=True, amount=chip_amount_to_mint)
                await asyncio.sleep(2)
            if unminted_piece > 0:
                piece_amount_to_mint = unminted_piece
                logger.info(
                    f"Key: ...{self.web3_utils.acct.key.hex()[30:]} | need to mint {piece_amount_to_mint} pieces")
                await self.mint(chip=False, amount=piece_amount_to_mint)
                await asyncio.sleep(2)
            if unminted_piece == 0 and unminted_chip == 0:
                logger.info(f"Key: ...{self.web3_utils.acct.key.hex()[30:]} | nothing to mint, minted_chips = {minted_chip}, minted_pieces = {minted_piece}")
                return
        except Exception as e:
            logger.error(f" {e}")
            await asyncio.sleep(2)

    @retry(stop=stop_after_attempt(5))
    async def get_info_for_mint(self, chip: bool, amount):
        json_data = {
            'addressThis': '0x00a9De8Af37a3179d7213426E78Be7DFb89F2b19' if chip else '0x2c085411ca401a84a9D98DEc415282FA239D53bB',
            'chainId': 204,
            'type': 'chip' if chip else 'chipPiece'
        }
        if chip:
            json_data['commodityToken'] = '0xe5116e725a8c1bF322dF6F5842b73102F3Ef0CeE'
        else:
            json_data['numPieces'] = amount

        response = await self.session.post("https://reiki.web3go.xyz/api/lottery/claim", proxy=self.proxy, json = json_data)
        responce_json = await response.json()
        result = responce_json.get("result")
        if result:
            nonce = responce_json.get("nonce")
            signature = responce_json.get("signature")
            event_id = responce_json.get("eventId")
            return nonce, signature, event_id
        else:
            logger.error(f"Key: ...{self.web3_utils.acct.key.hex()[30:]} | something went wrong with mint info: {responce_json}")

    @retry(stop=stop_after_attempt(5))
    async def finalize_mint_request(self, event_id):
        json_data = {
            'eventId': event_id
        }

        response = await self.session.post("https://reiki.web3go.xyz/api/lottery/claimSuccess", proxy=self.proxy, json = json_data)
        responce_json = await response.json()
        result = responce_json.get("result")
        if result:
            return True
        else:
            logger.error(f"Key: ...{self.web3_utils.acct.key.hex()[30:]} | something went wrong with claimSucces: {responce_json}")
    async def mint(self, chip: bool, amount):
        nonce, signature, event_id = await self.get_info_for_mint(chip=chip, amount=amount)
        w3_opbnb = Web3(Web3.HTTPProvider(
            'https://opbnb-mainnet-rpc.bnbchain.org'))

        chip_contract_address = w3_opbnb.to_checksum_address("0x00a9De8Af37a3179d7213426E78Be7DFb89F2b19")
        with open('inputs/chip_abi.json', 'r') as f:
            chip_abi = json.load(f)
        chip_contract = w3_opbnb.eth.contract(address=chip_contract_address, abi=chip_abi)

        piece_contract_address = w3_opbnb.to_checksum_address("0x2c085411ca401a84a9D98DEc415282FA239D53bB")
        with open('inputs/piece_abi.json', 'r') as f:
            piece_abi = json.load(f)
        piece_contract = w3_opbnb.eth.contract(address=piece_contract_address, abi=piece_abi)

        if chip:
            transaction = chip_contract.functions.safeBuyToken(addressThis=chip_contract_address,
                                                    _commodityToken=w3_opbnb.to_checksum_address("0xe5116e725a8c1bf322df6f5842b73102f3ef0cee"),
                                                    toAddress=self.web3_utils.acct.address,
                                                    chainId=204,
                                                    nonce=int(nonce, 16),
                                                   flatSig=signature).build_transaction({
                'value': 0,
                'from': self.web3_utils.acct.address,
                'nonce': w3_opbnb.eth.get_transaction_count(self.web3_utils.acct.address),
                'type': '0x2',
                'chainId': 204
            })
        else:
            transaction = piece_contract.functions.claim(addressThis=piece_contract_address,
                                                               toAddress=self.web3_utils.acct.address,
                                                               tokenId=0,
                                                               numPieces=amount,
                                                               chainId=204,
                                                               nonce=int(nonce, 16),
                                                               flatSig=signature).build_transaction({
                'value': 0,
                'from': self.web3_utils.acct.address,
                'nonce': w3_opbnb.eth.get_transaction_count(self.web3_utils.acct.address),
                'type': '0x2',
                'chainId': 204
            })

        estimated_gas = w3_opbnb.eth.estimate_gas(transaction)
        transaction['maxFeePerGas'] = w3_opbnb.to_wei(0.000010009, "gwei")
        transaction['maxPriorityFeePerGas'] = w3_opbnb.to_wei(0.00001, "gwei")
        transaction['gas'] = estimated_gas
        signed = self.web3_utils.acct.sign_transaction(transaction)
        # send transaction
        for _ in range(3):
            try:
                tx_hash = w3_opbnb.eth.send_raw_transaction(signed.rawTransaction)
                receipt = w3_opbnb.eth.wait_for_transaction_receipt(tx_hash, timeout=240)
                if receipt.status == 1:
                    logger.info(f"Key: ...{self.web3_utils.acct.key.hex()[30:]} | Mint transaction sent. Hash: {tx_hash.hex()}.")
                    await asyncio.sleep(10)
                    await self.finalize_mint_request(event_id)
                    return True, tx_hash.hex()
                else:
                    logger.error(f"Key: ...{self.web3_utils.acct.key.hex()[30:]} | Transaction failed, hash: {tx_hash.hex()}.")
                    return False, tx_hash.hex()
            except TimeExhausted as te:
                logger.error(f"Key: ...{self.web3_utils.acct.key.hex()[30:]} | Error checking transaction: {te}. Trying again...")
            except ValueError as ve:
                logger.warning(f"Key: ...{self.web3_utils.acct.key.hex()[30:]} | Not enough opBNB balance")
                logger.debug(ve)
                with open('no_balance_in_opbnb.txt',
                          'a') as file:
                    file.write(f"{self.web3_utils.acct.key.hex()} | {self.web3_utils.acct.address}\n")
                break
        logger.error(f"Key: ...{self.web3_utils.acct.key.hex()[30:]} | Did not manage to send transaction")
        return False, None

    async def send_to_master(self):
        w3_opbnb = Web3(Web3.HTTPProvider(
            'https://opbnb-mainnet-rpc.bnbchain.org'))
        piece_contract_address = w3_opbnb.to_checksum_address("0x2c085411ca401a84a9D98DEc415282FA239D53bB")
        with open('inputs/piece_abi.json', 'r') as f:
            piece_abi = json.load(f)
        piece_contract = w3_opbnb.eth.contract(address=piece_contract_address, abi=piece_abi)

        balance = piece_contract.functions.balanceOf(account=self.web3_utils.acct.address,
                                                     id=0).call()
        if balance >= config.MIN_PIECES_NUMBER_TO_SEND:
            transaction = piece_contract.functions.safeTransferFrom(self.web3_utils.acct.address,
                                                         to=w3_opbnb.to_checksum_address(config.MASTER_WALLET),
                                                         id=0,
                                                         amount=balance,
                                                            data=b''
                                                         ).build_transaction({
                'value': 0,
                'from': self.web3_utils.acct.address,
                'nonce': w3_opbnb.eth.get_transaction_count(self.web3_utils.acct.address),
                'type': '0x2',
                'chainId': 204
            })

            estimated_gas = w3_opbnb.eth.estimate_gas(transaction)
            transaction['maxFeePerGas'] = w3_opbnb.to_wei(0.000010009, "gwei")
            transaction['maxPriorityFeePerGas'] = w3_opbnb.to_wei(0.00001, "gwei")
            transaction['gas'] = estimated_gas
            signed = self.web3_utils.acct.sign_transaction(transaction)
            # send transaction
            for _ in range(3):
                try:
                    tx_hash = w3_opbnb.eth.send_raw_transaction(signed.rawTransaction)
                    receipt = w3_opbnb.eth.wait_for_transaction_receipt(tx_hash, timeout=240)
                    if receipt.status == 1:
                        logger.info(
                            f"Key: ...{self.web3_utils.acct.key.hex()[30:]} | Sent all pieces to master wallet. Hash: {tx_hash.hex()}.")
                        await asyncio.sleep(10)
                        return True, tx_hash.hex()
                    else:
                        logger.error(
                            f"Key: ...{self.web3_utils.acct.key.hex()[30:]} | Transaction failed, hash: {tx_hash.hex()}.")
                        return False, tx_hash.hex()
                except TimeExhausted as te:
                    logger.error(
                        f"Key: ...{self.web3_utils.acct.key.hex()[30:]} | Error checking transaction: {te}. Trying again...")
                except ValueError as ve:
                    logger.warning(
                        f"Key: ...{self.web3_utils.acct.key.hex()[30:]} | Not enough opBNB balance")
                    logger.debug(ve)
                    with open('no_balance_in_opbnb.txt',
                              'a') as file:
                        file.write(f"{self.web3_utils.acct.key.hex()} | {self.web3_utils.acct.address}\n")
                    break
            logger.error(
                f"Key: ...{self.web3_utils.acct.key.hex()[30:]} | Did not manage to send transaction")
            return False, None

    @retry(stop=stop_after_attempt(5))
    async def get_chip_id(self):
        response = await self.session.get("https://reiki.web3go.xyz/api/lottery/mint/chip/any", proxy=self.proxy)
        responce_json = await response.json()
        token_id = responce_json.get("tokenId")
        if token_id:
            return token_id
        else:
            logger.error(f"Key: ...{self.web3_utils.acct.key.hex()[30:]} | something went wrong with getting chip id: {responce_json}")
            return None

    async def send_burn_transaction(self, token_id):
        method = '0x42966c68'
        p1 = hex(int(token_id))[2:].zfill(64)
        data = method + p1
        estimation_transaction = {
            'from': self.web3_utils.acct.address,
            'to': self.web3_utils.w3.to_checksum_address('0xe5116e725a8c1bf322df6f5842b73102f3ef0cee'),
            'nonce': self.web3_utils.w3.eth.get_transaction_count(self.web3_utils.acct.address),
            'data': data,
            'type': '0x2',
            'chainId': 204
        }
        estimated_gas = self.web3_utils.w3.eth.estimate_gas(estimation_transaction)
        transaction = {
            'from': self.web3_utils.acct.address,
            'to': self.web3_utils.w3.to_checksum_address('0xe5116e725a8c1bf322df6f5842b73102f3ef0cee'),
            'gas': estimated_gas,
            'maxFeePerGas': self.web3_utils.w3.to_wei(0.000010009, "gwei"),
            'maxPriorityFeePerGas': self.web3_utils.w3.to_wei(0.00001, "gwei"),
            'nonce': self.web3_utils.w3.eth.get_transaction_count(self.web3_utils.acct.address),
            'data': data,
            'type': '0x2',
            'chainId': 204
        }

        signed = self.web3_utils.acct.sign_transaction(transaction)
        # send transaction
        for _ in range(3):
            try:
                tx_hash = self.web3_utils.w3.eth.send_raw_transaction(signed.rawTransaction)
                receipt = self.web3_utils.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=240)
                if receipt.status == 1:
                    logger.info(
                        f"Key: ...{self.web3_utils.acct.key.hex()[30:]} | Sent all pieces to master wallet. Hash: {tx_hash.hex()}.")
                    await asyncio.sleep(10)
                    return True, tx_hash.hex()
                else:
                    logger.error(
                        f"Key: ...{self.web3_utils.acct.key.hex()[30:]} | Transaction failed, hash: {tx_hash.hex()}.")
                    return False, tx_hash.hex()
            except TimeExhausted as te:
                logger.error(
                    f"Key: ...{self.web3_utils.acct.key.hex()[30:]} | Error checking transaction: {te}. Trying again...")
            except ValueError as ve:
                logger.warning(
                    f"Key: ...{self.web3_utils.acct.key.hex()[30:]} | Not enough opBNB balance")
                logger.debug(ve)
                with open('no_balance_in_opbnb.txt',
                          'a') as file:
                    file.write(f"{self.web3_utils.acct.key.hex()} | {self.web3_utils.acct.address}\n")
                break
            logger.error(
                f"Key: ...{self.web3_utils.acct.key.hex()[30:]} | Did not manage to send transaction")

    @retry(stop=stop_after_attempt(5))
    async def send_burn_info(self, token_id, hash):
        json_data = {
            'tokenId': token_id,
            'txHash': hash
        }
        response = await self.session.post(url="https://reiki.web3go.xyz/api/lottery/burn", proxy=self.proxy, json=json_data)
        if response.status == 201:
            return

    async def burn_chip(self):
        token_id = await self.get_chip_id()
        if token_id is not None:
            result, hash = await self.send_burn_transaction(token_id)
            if result:
                await self.send_burn_info(token_id, hash)
                await asyncio.sleep(4)
                await self.loterry_sync()