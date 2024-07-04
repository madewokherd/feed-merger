import json
import urllib.parse
import urllib.request

def get_token(server_url, state):
    if ('mastodon', server_url, 'token') in state:
        return state[('mastodon', server_url, 'token')]

    scope = 'read:statuses read:lists'

    # register application
    register_url = urllib.parse.urlparse(server_url)._replace(path="/api/v1/apps").geturl()
    register_data = urllib.parse.urlencode({
        'client_name': 'feed-merger',
        'redirect_uris': 'urn:ietf:wg:oauth:2.0:oob',
        'scopes': scope,
        'website': 'https://madewokherd.nfshost.com/omgsecret/feed-merger.txt',
    }).encode('utf8')
    register_response = json.load(urllib.request.urlopen(register_url, data=register_data))

    # authorize (log in as user)
    authorize_query = urllib.parse.urlencode({
        'response_type': 'code',
        'client_id': register_response['client_id'],
        'redirect_uri': 'urn:ietf:wg:oauth:2.0:oob',
        'scope': scope,
    })
    authorize_url = urllib.parse.urlparse(server_url)._replace(path="/oauth/authorize", query=authorize_query).geturl()

    print("Please visit this website:", authorize_url)
    oauth_code = input("Enter OAuth code: ")

    # get token
    token_url = urllib.parse.urlparse(server_url)._replace(path="/oauth/token").geturl()
    token_data = urllib.parse.urlencode({
        'grant_type': 'authorization_code',
        'code': oauth_code,
        'client_id': register_response['client_id'],
        'client_secret': register_response['client_secret'],
        'redirect_uri': 'urn:ietf:wg:oauth:2.0:oob',
        'scope': scope,
    }).encode('utf8')
    token_response = json.load(urllib.request.urlopen(token_url, data=token_data))

    token = token_response['access_token']
    state[('mastodon', server_url, 'token')] = token

    return token

def format_status(status, status_url):
    if status.get('reblog'):
        content = f"<p>{status['account']['display_name']} reblogged:</p><p><img src=\"{status['reblog']['account']['avatar']}\" width=32 height=32> {status['reblog']['account']['display_name']}</p>{format_status(status['reblog'], status_url)}"
    elif status.get('spoiler_text'):
        content = f"<p><a href=\"{status_url}\">CW: {status['spoiler_text']}</a></p>"
    else:
        content = status['content']

    media_attachments = status.get('media_attachments')
    if media_attachments:
        for a in media_attachments:
            content += f"<p>[{a['type']}]</p>"
            content += f"<p><a href=\"{a['url']}\"><img src=\"{a['preview_url']}\"></a></p>"
            if a.get('description'):
                content += f"<p>Description: {a['description']}</p>"

    a = status.get('card')
    if a:
        if a.get('author_name'):
            content += f"<p>[{a.get('provider_name')}] {a['author_name']} - {a.get('title')}</p>"
        else:
            content += f"<p>[{a.get('provider_name')}] {a.get('title')}</p>"
        content += f"<p><a href=\"{a['url']}\"><img src=\"{a['image']}\"></a></p>"
        if a.get('description'):
            content += f"<p>Description: {a['description']}</p>"

    return content

def process(line, state, items):
    line = line.split(':', 1)[1] #remove mastodon:
    parse = urllib.parse.urlparse(line)
    server_url = parse._replace(fragment="", query="", path="").geturl()
    timeline_parse = parse._replace(fragment="")
    timeline_url = timeline_parse.geturl()
    query_dict = urllib.parse.parse_qs(parse.query)
    token = get_token(server_url, state)

    matching = None
    nonmatching = None
    timeline_key = None
    if parse.fragment:
        for pair in parse.fragment.split('&'):
            key, value = pair.split('=', 1)
            if key == 'matching':
                matching = value.split()
            elif key == 'nonmatching':
                nonmatching = value.split()
            elif key == 'key':
                timeline_key = value

    since_id = state.get(('mastodon', timeline_url, timeline_key, 'since_id'))
    if since_id:
        query_dict['since_id'] = since_id

    query_dict['limit'] = 40

    new_since_id = None

    while True:
        query_url = timeline_parse._replace(query = urllib.parse.urlencode(query_dict)).geturl()

        query_request = urllib.request.Request(query_url, headers = {'Authorization': 'Bearer ' + token})
        json_response = json.load(urllib.request.urlopen(query_request))

        if new_since_id is None and json_response:
            new_since_id = json_response[0]['id']

        for item in json_response:
            if item.get('reblog'):
                status_url = parse._replace(fragment="", query="", path=f"/web/statuses/{item['reblog']['id']}").geturl()
            else:
                status_url = parse._replace(fragment="", query="", path=f"/web/statuses/{item['id']}").geturl()

            content = format_status(item, status_url)

            if matching and not any(x for x in matching if x in content.lower()):
                continue

            if nonmatching and any(x for x in nonmatching if x in content.lower()):
                continue

            items.append((f"""

<h1><a href="{status_url}"><img src="{item['account']['avatar']}" width=48 height=48> {item['account']['display_name']} [{item['account']['acct']}] at {item['created_at']} </a><a name="{item['id']}" href="#{item['id']}">[anchor]</a></h1>

{content}

""", item['created_at']))

        if since_id and len(json_response) == 40:
            query_dict['max_id'] = json_response[-1]['id']
        else:
            break

    if new_since_id:
        state[('mastodon', timeline_url, timeline_key, 'since_id')] = new_since_id

