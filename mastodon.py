import html
import json
import urllib.parse
import urllib.request

import core

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

def account_name(account):
    return account.get('display_name') or account.get('username') or ''

def format_status(status, link, reblog_author):
    html_parts = []
    html_end_parts = []

    if reblog_author:
        html_parts.append(f"<p><img src=\"{reblog_author['avatar']}\" width=16 height=16> {account_name(reblog_author)} boosted:</p>")

    if status.get('in_reply_to_id'):
        reply_link = urllib.parse.urlparse(link)._replace(fragment="", query="", path=f"/web/statuses/{status['in_reply_to_id']}").geturl()
        html_parts.append(f"<p><img src=\"{status['account']['avatar']}\" width=16 height=16> {account_name(status['account'])} replied to <a href=\"{reply_link}\">a post</a></p>")

    if status.get('spoiler_text'):
        html_parts.append(f"<details><summary>{html.escape(status['spoiler_text'])}</summary>")
        html_end_parts.append("</details>")

    html_parts.append(status['content'])

    media_attachments = status.get('media_attachments')
    if media_attachments:
        for a in media_attachments:
            html_parts.append(f"<p>[{a['type']}]</p>")
            images = [a[i] for i in ['preview_url', 'url', 'preview_remote_url', 'remote_url'] if a.get(i)]
            if images:
                img_tags = f'''<img src="{images[-1]}">'''
                for img in images[-2::-1]:
                    img_tags = f'''<object data="{img}">{img_tags}</object>'''
                html_parts.append(f"<p><a href=\"{a['url']}\">{img_tags}</a></p>")
            if a.get('description'):
                html_parts.append(f"""<p style="white-space: pre-wrap;">Description: {html.escape(a['description'])}</p>""")

    a = status.get('card')
    if a:
        if a.get('author_name'):
            html_parts.append(f"<p>[{a.get('provider_name')}] {a['author_name']} - {a.get('title')}</p>")
        else:
            html_parts.append(f"<p>[{a.get('provider_name')}] {a.get('title')}</p>")
        if a.get('image'):
            html_parts.append(f"<p><a href=\"{a['url']}\"><img src=\"{a['image']}\"></a></p>")
        if a.get('description'):
            html_parts.append(f"<p>Description: {html.escape(a['description'])}</p>")

    html_end_parts.reverse()
    html_parts.extend(html_end_parts)

    return '\n'.join(html_parts)

def process(line, state):
    line = line.split(':', 1)[1] #remove mastodon:
    parse = urllib.parse.urlparse(line)
    server_url = parse._replace(fragment="", query="", path="").geturl()
    timeline_parse = parse._replace(fragment="")
    timeline_url = timeline_parse.geturl()
    query_dict = urllib.parse.parse_qs(parse.query)
    token = get_token(server_url, state)
    j = {'fm:entries': []}

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

        j['fm:entries'].extend(json_response)

        if since_id and len(json_response) == 40:
            query_dict['max_id'] = json_response[-1]['id']
        else:
            break

    for item in j['fm:entries']:
        if item.get('reblog'):
            main_item = item['reblog']
            reblog_author = item['account']
        else:
            main_item = item
            reblog_author = None

        item['fm:link'] = parse._replace(fragment="", query="", path=f"/web/statuses/{main_item['id']}").geturl()
        item['fm:avatar'] = main_item['account']['avatar']
        item['fm:author'] = account_name(main_item['account'])
        item['fm:title'] = main_item['account']['acct']
        item['fm:timestamp'] = item['created_at']

        item['fm:html'] = format_status(main_item, item['fm:link'], reblog_author)

    if new_since_id:
        state[('mastodon', timeline_url, timeline_key, 'since_id')] = new_since_id

    return core.JSON, j

