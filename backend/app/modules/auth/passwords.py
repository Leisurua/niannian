import hashlib
import hmac
import secrets

from anyio import CapacityLimiter, to_thread

_iterations = 600_000
_limiter = CapacityLimiter(4)


async def _derive(password: str, salt: bytes) -> bytes:
    return await to_thread.run_sync(
        hashlib.pbkdf2_hmac, "sha256", password.encode(), salt, _iterations, limiter=_limiter
    )


async def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    proof = await _derive(password, salt)
    return f"pbkdf2_sha256${_iterations}${salt.hex()}${proof.hex()}"


async def verify_password(password: str, stored: str | None) -> bool:
    if stored is None:
        await _derive(password, bytes(16))
        return False
    try:
        algorithm, iterations, salt, proof = stored.split("$")
        if (algorithm, iterations) != ("pbkdf2_sha256", str(_iterations)):
            return False
        return hmac.compare_digest(await _derive(password, bytes.fromhex(salt)), bytes.fromhex(proof))
    except ValueError:
        return False
