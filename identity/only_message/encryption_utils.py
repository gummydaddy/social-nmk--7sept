from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key, load_pem_public_key
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization


def generate_key_pair():
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048
    )
    public_key = private_key.public_key()
    return private_key, public_key

def serialize_key(key, is_private=False):
    if is_private:
        return key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ).decode()
    else:
        return key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode()

def encrypt_message(message, key):
    f = Fernet(key)
    return f.encrypt(message.encode()).decode()


def decrypt_message(encrypted_message, key):
    if not encrypted_message:
        return None  # Handle None or empty encrypted_message gracefully
    f = Fernet(key)
    try:
        return f.decrypt(encrypted_message.encode()).decode()
    except InvalidToken:
        return None  # Handle decryption failure gracefully
    

def sign_message(message, private_key):
    if not message:
        return None  # Handle empty message
    private_key = load_pem_private_key(private_key.encode(), password=None)
    signature = private_key.sign(
        message.encode(),
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH
        ),
        hashes.SHA256()
    )
    return signature.hex()


def verify_message(message, signature, public_key):
    if not message or not signature:
        return False  # Handle empty message or signature
    public_key = load_pem_public_key(public_key.encode())
    try:
        public_key.verify(
            bytes.fromhex(signature),
            message.encode(),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        return True
    except Exception as e:
        return False

