# nmk_chain/utils.py

from .models import Block as BlockModel
from .blockchain import Block, Blockchain  # Import the Block and Blockchain classes from blockchain.py
from only_card.models import AuthUser  # Use the AuthUser model from only_card

class InvalidTransactionException(Exception):
    pass

class InsufficientFundsException(Exception):
    pass

def send_money(sender, recipient, amount):
    try:
        amount = float(amount)
    except ValueError:
        raise InvalidTransactionException("Invalid Transaction.")
    if amount <= 0.00:
        raise InvalidTransactionException("Invalid Transaction.")
    sender_balance = get_balance(sender)
    if amount > sender_balance and sender != "BANK":
        raise InsufficientFundsException("Insufficient Funds.")
    if sender == recipient:
        raise InvalidTransactionException("Invalid Transaction.")
    if not AuthUser.objects.filter(username=recipient).exists():
        raise InvalidTransactionException("User Does Not Exist.")
    blockchain = get_blockchain()
    number = len(blockchain.chain) + 1
    previous_hash = blockchain.chain[-1].hash() if blockchain.chain else '0'
    data = f"{sender}-->{recipient}-->{amount}"
    new_block = Block(number, previous_hash, data)
    blockchain.mine(new_block)
    sync_blockchain(blockchain)

def get_balance(username):
    balance = 0.00
    blockchain = get_blockchain()
    for block in blockchain.chain:
        data = block.data.split("-->")
        if len(data) != 3:
            continue  # Skip invalid transactions
        if username == data[0]:
            balance -= float(data[2])
        elif username == data[1]:
            balance += float(data[2])
    return balance

def get_blockchain():
    blockchain = Blockchain()
    for block_model in BlockModel.objects.all():
        block = Block(block_model.number, block_model.previous, block_model.data, block_model.nonce)
        blockchain.add(block)
    return blockchain

def sync_blockchain(blockchain):
    BlockModel.objects.all().delete()
    for block in blockchain.chain:
        BlockModel.objects.create(number=block.number, hash=block.hash(), previous=block.previous_hash, data=block.data, nonce=block.nonce)
