import os
TOKEN_FILE = "client_token.txt"


def save_token(token):
    with open(TOKEN_FILE, "w") as f:
        f.write(token)


def load_token():
    if not os.path.exists(TOKEN_FILE):
        return None
    return open(TOKEN_FILE).read().strip()
