import json
import base64
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.exceptions import InvalidSignature

def b64url_dec(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))

def bytes_to_int(b: bytes) -> int:
    return int.from_bytes(b, byteorder='big')

jwk = {
    "kty": "RSA",
    "n": "v1...",  # base64url encoded
    "e": "AQAB"
}
# n_bytes = b64url_dec(jwk["n"])
# e_bytes = b64url_dec(jwk["e"])
# public_numbers = rsa.RSAPublicNumbers(e=bytes_to_int(e_bytes), n=bytes_to_int(n_bytes))
# public_key = public_numbers.public_key()
# public_key.verify(signature, msg, padding.PKCS1v15(), hashes.SHA256())
print("Syntax OK")
