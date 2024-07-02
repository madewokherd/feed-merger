
def get_token(state, force=False):
    if not force and state.get(('github', 'token')):
        return state['github', 'token']

    print("Please visit https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#creating-a-fine-grained-personal-access-token and follow the instructions to create an access token")
    print("The token doesn't need any permissions beyond read-only access to any repositories you want to follow.")
    token = input("Enter token: ")

    state['github', 'token'] = token
    return token

def process(line, state, items):
    token = get_token(state)

