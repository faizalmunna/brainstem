def validate_login_token(token: str) -> bool:
    return bool(token) and token.startswith("login_")
