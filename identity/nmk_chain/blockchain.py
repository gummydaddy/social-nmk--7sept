# nmk_chain/blockchain.py

class Block:
    def __init__(self, number, previous_hash, data, nonce=0):
        self.number = number
        self.previous_hash = previous_hash
        self.data = data
        self.nonce = nonce

    def hash(self):
        import hashlib
        block_string = f"{self.number}{self.previous_hash}{self.data}{self.nonce}"
        return hashlib.sha256(block_string.encode()).hexdigest()

class Blockchain:
    def __init__(self):
        self.chain = []
        self.create_genesis_block()

    def create_genesis_block(self):
        genesis_block = Block(0, "0", "Genesis Block")
        self.chain.append(genesis_block)

    def add(self, block):
        self.chain.append(block)

    def mine(self, block):
        while not self.is_valid_proof(block):
            block.nonce += 1
        self.add(block)

    def is_valid_proof(self, block):
        guess_hash = block.hash()
        return guess_hash[:4] == "0000"
