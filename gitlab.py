import urllib.parse

def get_token(url, state):
    host = urllib.parse.urlparse(url)._replace(fragment="", query="", path="").geturl()

    if state.get(('gitlab', host, 'token')):
        return state['gitlab', host, 'token']

    token_pref_url = urllib.parse.urlparse(url)._replace(fragment="", query="", path="/-/user_settings/personal_access_tokens").geturl()

    print(f"Please generate a token at {token_pref_url}")
    print("It should have the read_repository scope")
    token = input("Enter token: ")

    state['gitlab', host, 'token'] = token
    return token

def process_branch(line, state, items):
    get_token(line, state)

def process(line, state, items):
    prefix, line = line.split(':', 1)

    if prefix == 'gitlab-branch':
        process_branch(line, state, items)

