from . import tokens


def login(token: str) -> bool:
    return tokens.validate_login_token(token)
