import _thread
import base64
import datetime
import html
import http.server
import json
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request

import agegate

from html import escape as e

_USER_AGENT = f"{sys.platform}:feed-merger:v1 (by /u/migratingwoks)"

_oauth_error = None
_oauth_state = None
_oauth_token = None

class OAuthHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if not q.get('state') or q['state'][0] != _oauth_state:
            self.send_error(403, "Forbidden", "Incorrect or missing OAuth state")
            return
        self.send_response(200, "OK")
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        if q.get('error'):
            global _oauth_error
            _oauth_error = q['error'][0]
            self.wfile.write(b"Error reported from reddit: " + _oauth_error.encode('utf8'))
        else:
            global _oauth_code
            _oauth_code = q['code'][0]
            self.wfile.write(b"The request succeeded")
        _thread.start_new_thread(self.server.shutdown, ())

def get_client_creds(state):
    if ('reddit', 'client_creds') in state:
        return state['reddit', 'client_creds']

    print("Hi, I'm going to need client credentials to function. You can either contact u/migratingwoks for this, or generate them at https://www.reddit.com/prefs/apps (you can also use that page to revoke this app's access in the future).")
    client_id = input("Enter client ID: ")
    client_secret = input('Enter client secret (leave this blank if client ID is for an "installed app"): ')

    state['reddit', 'client_creds'] = client_id, client_secret
    return client_id, client_secret

def get_token(state, force=False):
    if not force and state.get(('reddit', 'token')):
        return state['reddit', 'token']

    client_id, client_secret = get_client_creds(state)

    client_auth_token = base64.b64encode(f'{client_id}:{client_secret}'.encode('utf8')).decode('ascii')
    client_auth_header = {'Authorization': 'Basic ' + client_auth_token, 'User-Agent': _USER_AGENT}

    if state.get(('reddit', 'refresh_token')):
        refresh_token = state['reddit', 'refresh_token']
        refresh_url = "https://www.reddit.com/api/v1/access_token"
        refresh_data = urllib.parse.urlencode({
            'client_id': client_id,
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
        }).encode('utf8')
        try:
            req = urllib.request.Request(refresh_url, data=refresh_data, headers=client_auth_header)
            token_response = json.load(urllib.request.urlopen(req))
        except urllib.error.HTTPError as e:
            if e.code != 401:
                raise
        else:
            token = token_response['access_token']
            state[('reddit', 'token')] = token

            return token

    scope = "read"

    global _oauth_state
    global _oauth_code
    global _oauth_error
    _oauth_state = secrets.token_urlsafe()
    _oauth_code = None
    _oauth_error = None

    authorize_query = urllib.parse.urlencode({
        'client_id': client_id,
        'response_type': 'code',
        'state': _oauth_state,
        'redirect_uri': 'http://localhost:8080',
        'duration': 'permanent',
        'scope': scope,
    })
    authorize_url = urllib.parse.urlparse("https://www.reddit.com/api/v1/authorize")._replace(query=authorize_query).geturl()

    print(f"Please visit this website and login:", authorize_url)

    # start server and wait for code
    httpd = http.server.HTTPServer(('localhost', 8080), OAuthHandler)
    httpd.serve_forever()

    if _oauth_error is not None:
        raise Exception(_oauth_error)

    code = _oauth_code

    # get token
    token_url = "https://www.reddit.com/api/v1/access_token"
    token_data = urllib.parse.urlencode({
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': 'http://localhost:8080',
    }).encode('utf8')
    req = urllib.request.Request(token_url, headers=client_auth_header)
    token_response = json.load(urllib.request.urlopen(req, data=token_data))

    token = token_response['access_token']
    state[('reddit', 'token')] = token
    state[('reddit', 'refresh_token')] = token_response['refresh_token']

    return token

def api_request(state, url):
    token = get_token(state)

    req = urllib.request.Request(url, headers = {'Authorization': 'Bearer ' + token, 'User-Agent': _USER_AGENT})

    try:
        return json.load(urllib.request.urlopen(req))
    except urllib.error.HTTPError as e:
        if e.code == 401:
            token = get_token(state, True)
            req = urllib.request.Request(url, headers = {'Authorization': 'Bearer ' + token, 'User-Agent': _USER_AGENT})
            return json.load(urllib.request.urlopen(req))
        print(e.fp.read())
        raise

def process_subreddit(subreddit, state, items):
    latest = state.get(('reddit', 'subreddit', subreddit, 'latest'))
    new_latest = None
    last = None

    url = f"https://oauth.reddit.com/r/{subreddit}/new"

    if latest:
        query = urllib.parse.urlencode({
            'before': latest,
            'limit': 100,
            'raw_json': 1,
        })
    else:
        query = urllib.parse.urlencode({
            'raw_json': 1,
        })

    count = 0

    while True:
        url = urllib.parse.urlparse(url)._replace(query=query).geturl()

        json = api_request(state, url)

        j = json['data']

        for child in j['children']:
            entry = child['data']

            if new_latest is None:
                new_latest = entry['name']

            if entry['over_18'] and not agegate.check(state):
                continue
            
            content = e(entry['selftext']).replace('\n', '<br>')

            posted = datetime.datetime.fromtimestamp(entry['created'], datetime.timezone.utc).isoformat()

            items.append((f"""

<h1><a href="https://www.reddit.com/{entry['permalink']}">r/{subreddit} - {e(entry['author'])} - {e(entry['title'])}</a> {posted} <a name="{entry['name']}" href="#{entry['name']}">[anchor]</a></h1>

{entry['selftext_html']}
""", posted))

        if not latest or not j.get('after'):
            break

        query = urllib.parse.urlencode({
            'before': latest,
            'after': j['after'],
            'limit': 100,
            'raw_json': 1,
        })

    state['reddit', 'subreddit', subreddit, 'latest'] = new_latest or latest

def process(line, state, items):
    line = line.split(':', 1)[1] # remove reddit:

    prefix, rest = line.split('/', 1)
    if prefix == 'r':
        # subreddit
        subreddit = rest

        process_subreddit(rest, state, items)
    else:
        raise Exception("unknown prefix")
