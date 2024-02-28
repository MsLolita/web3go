from eth_account import Account
from eth_account.messages import encode_defunct, SignableMessage, encode_structured_data
from web3 import Web3


class Web3Utils:
    def __init__(self, http_provider: str = 'https://eth.llamarpc.com', mnemonic: str = None, key: str = None):
        self.w3 = None
        Account.enable_unaudited_hdwallet_features()

        if mnemonic:
            self.mnemonic = mnemonic
            self.acct = Account.from_mnemonic(mnemonic)
        elif key:
            self.mnemonic = ""
            self.acct = Account.from_key(key)

        self.define_new_provider(http_provider)

    def __str__(self):
        return f"{self.acct.address[:10]}...{self.acct.address[-10:]}"

    def define_new_provider(self, http_provider: str):
        self.w3 = Web3(Web3.HTTPProvider(http_provider))

    def create_wallet(self):
        self.acct, self.mnemonic = Account.create_with_mnemonic()
        return self.acct, self.mnemonic

    def sign(self, encoded_msg: SignableMessage):
        return self.w3.eth.account.sign_message(encoded_msg, self.acct.key)

    def get_signed_code(self, msg) -> str:
        return self.sign(encode_defunct(text=msg)).signature.hex()

    def get_signed_code_struct(self, msg) -> str:
        return self.sign(encode_structured_data(msg)).signature.hex()
