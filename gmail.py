import base64
import datetime
import json
import urllib.error
import urllib.parse
import urllib.request

def get_client_credentials(state):
    if ('gmail', 'client_credentials') in state:
        return state['gmail', 'client_credentials']

    print("""This requires a google cloud project
# create a project: https://console.cloud.google.com/projectcreate
# enable Gmail API here: https://console.cloud.google.com/workspace-api/products
# configure consent here: https://console.cloud.google.com/apis/credentials/consent
# create an OAuth Client ID: https://console.cloud.google.com/apis/credentials
#  Application type: Desktop app
""")
    client_id = input("Enter client id: ")
    client_secret = input("Enter client secret: ")

    state['gmail', 'client_credentials'] = client_id, client_secret

    return client_id, client_secret

def get_token(user, state, force=False):
    if not force and state.get(('gmail', user, 'token')):
        return state['gmail', user, 'token']

    client_id, client_secret = get_client_credentials(state)

    if state.get(('gmail', user, 'refresh_token')):
        refresh_token = state['gmail', user, 'refresh_token']
        refresh_url = "https://www.googleapis.com/oauth2/v4/token"
        refresh_data = urllib.parse.urlencode({
            'grant_type': 'refresh_token',
            'client_id': client_id,
            'client_secret': client_secret,
            'refresh_token': refresh_token,
        }).encode('utf8')
        try:
            token_response = json.load(urllib.request.urlopen(refresh_url, data=refresh_data))
        except urllib.error.HTTPError as e:
            if e.code not in (400, 401):
                raise
        else:
            token = token_response['access_token']
            state[('gmail', user, 'token')] = token

            return token

    scope = "https://www.googleapis.com/auth/gmail.readonly"

    authorize_query = urllib.parse.urlencode({
        'response_type': 'code',
        'client_id': client_id,
        'redirect_uri': 'urn:ietf:wg:oauth:2.0:oob',
        'scope': scope,
        'access_type': 'offline',
    })
    authorize_url = urllib.parse.urlparse("https://accounts.google.com/o/oauth2/auth")._replace(query=authorize_query).geturl()

    print(f"Please visit this website and login as {user}:", authorize_url)
    oauth_code = input("Enter Authorization code: ")

    # get token
    token_url = "https://www.googleapis.com/oauth2/v4/token"
    token_data = urllib.parse.urlencode({
        'grant_type': 'authorization_code',
        'code': oauth_code,
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': 'urn:ietf:wg:oauth:2.0:oob',
        'scope': scope,
    }).encode('utf8')
    token_response = json.load(urllib.request.urlopen(token_url, data=token_data))

    token = token_response['access_token']
    state[('gmail', user, 'token')] = token
    state[('gmail', user, 'refresh_token')] = token_response['refresh_token']

    return token

def format_body(b, mime_type = 'text/plain'):
    if 'data' not in b:
        return None

    data = base64.urlsafe_b64decode(b['data'] + '=' * (4 - len(b['data']) % 4)).decode(encoding='utf8', errors='replace')

    if 'plain' in mime_type:
        if data.strip():
            data = '<p>' + data.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>') + '</p>'
        else:
            data = None
    else:
        if '<body' in data:
            data = data.split('<body', 1)[1].split('>', 1)[-1]
        if '</body>' in data:
            data = data.split('</body>', 1)[0]

    return data

def format_message(user, m):
    p = m['payload']

    subject = None
    sender = None
    date = None
    content_type = 'text/plain'

    for h in p['headers']:
        if h['name'] == 'From':
            sender = h['value']
        elif h['name'] == 'Subject':
            subject = h['value']
        elif h['name'] == 'Date':
            date = h['value']
        elif h['name'] == 'Content-Type':
            content_type = h['value']

    body = format_body(p['body'], content_type)

    if not body:
        for part in p['parts']:
            if 'text/html' in part['mimeType'] and part.get('body'):
                body = format_body(part['body'], part['mimeType'])
            if body:
                break

    if not body:
        for part in p['parts']:
            if 'text/plain' in part['mimeType'] and part.get('body'):
                body = format_body(part['body'], part['mimeType'])
            if body:
                break

    message_link = f"https://mail.google.com/mail/u/{user}/?view=pt&search=all&permmsgid=msg-f:{int(m['id'], 16)}"
    thread_link = f"https://mail.google.com/mail/u/{user}/popout?search=all&th=%23thread-f:{int(m['threadId'], 16)}"

    return f"""
<h1>{sender} <a href="{message_link}">{subject}</a> <a href="{thread_link}">{date}</a> <a name="{m['id']}" href="#{m['id']}">[anchor]</a></h1>

{body}
"""

def api_request(user, state, url, data=None):
    token = get_token(user, state)

    while True:
        req = urllib.request.Request(url, data = data, headers = {'Authorization': 'Bearer ' + token})

        try:
            return json.load(urllib.request.urlopen(req))
        except urllib.error.HTTPError as e:
            if e.code in (400, 401):
                token = get_token(user, state, True)
                continue
        else:
            break

def process(line, state, items):
    line = line.split(':', 1)[1] #remove gmail:
    user, query = line.split('/')

    prev_latest = state.get(('gmail', user, query, 'latest_id'))
    current_latest = None

    messages_query = urllib.parse.urlencode({'q': query})

    while True:
        messages_url = urllib.parse.urlparse(f"https://gmail.googleapis.com/gmail/v1/users/{user}/messages")._replace(
            query = messages_query).geturl()

        json_response = api_request(user, state, messages_url)

        if json_response['messages'] and not current_latest:
            current_latest = json_response['messages'][0]['id']

        done = False

        for m in json_response['messages']:
            id = m['id']

            if prev_latest and int(id, 16) <= int(prev_latest, 16):
                done = True
                break

            message_url = f"https://gmail.googleapis.com/gmail/v1/users/{user}/messages/{id}?format=full"

            m = api_request(user, state, message_url)

            items.append((format_message(user, m), datetime.datetime.fromtimestamp(int(m['internalDate'])/1000, datetime.timezone.utc).isoformat()))

        if done or not json_response.get('nextPageToken') or not prev_latest:
            break

        messages_query = urllib.parse.urlencode({'q': query, 'pageToken': json_response["nextPageToken"]})

    state['gmail', user, query, 'latest_id'] = current_latest or prev_latest

