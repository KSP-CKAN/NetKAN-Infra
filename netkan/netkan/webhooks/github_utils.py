from functools import wraps
import hashlib
import hmac
from flask import current_app, request
from typing import Callable, Tuple, Any, Dict, Optional


def signature_required(func: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(func)
    def decorated_function(*args: Any, **kwargs: Any) -> Tuple[str, int]:
        # Make sure it's from GitHub
        if not sig_match(request.headers.get('X-Hub-Signature'), request.data):
            current_app.logger.warning('X-Hub-Signature did not match the request data')
            return 'Signature mismatch', 400
        return func(*args, **kwargs)
    return decorated_function


def sig_match(req_sig: Optional[str], body: bytes) -> bool:
    # Make sure a secret is defined in our config
    hook_secret = current_app.config['secret']
    if not hook_secret:
        current_app.logger.warning('No secret is configured')
        return False
    # Make sure a sig was sent
    if req_sig is None:
        current_app.logger.warning('No signature provided in the request')
        return False
    # Make sure they match
    # compare_digest takes the same time regardless of how similar the strings are
    # (to make it harder for hackers)
    secret_sig = "sha1=" + hmac.new(hook_secret.encode('ascii'), body, hashlib.sha1).hexdigest()
    return hmac.compare_digest(req_sig, secret_sig)
