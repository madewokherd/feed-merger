import getpass
import html
import urllib.parse

import atproto

import core

client = None

def get_client(state):
    global client
    if client is None:
        client = atproto.Client()

        if ('bluesky', 'session') in state:
            client.login(session_string = state['bluesky', 'session'])
        else:
            username = input("Enter bluesky username: ")
            password = getpass.getpass()
            client.login(login=username, password=password)

        def on_session_change(event, session):
            state['bluesky', 'session'] = session.export()

        client.on_session_change(on_session_change)
        state['bluesky', 'session'] = client.export_session_string()
    return client

def to_json(obj):
    if type(obj) is list:
        result = []
        for i in obj:
            result.append(to_json(i))
        return result
    if type(obj) in (dict, str, int, float, bool) or obj is None:
        return obj
    result = dict(obj)
    for key in list(result.keys()):
        result[key] = to_json(result[key])
    return result

def uri_to_https(uri):
    parse = urllib.parse.urlparse(uri)
    if parse.scheme != 'at':
        return 'uri'
    else:
        did = parse.netloc
        collection, rkey = parse.path.lstrip('/').split('/', 1)
        if collection == 'app.bsky.feed.post':
            return f'https://bsky.app/profile/{did}/post/{rkey}'
        else:
            return 'uri'

def post_to_html(entry, doc, line, state, url):
    html_parts = []

    if entry['py_type'] == 'app.bsky.feed.defs#feedViewPost':
        if entry.get('reason'):
            reason = entry['reason']['py_type']
            if reason == 'app.bsky.feed.defs#reasonRepost':
                entry['fm:timestamp'] = entry['reason']['indexed_at']
                html_parts.append(f'''<p><img src="{entry['reason']['by']['avatar']}" width=16 height=16> {html.escape(entry['reason']['by']['display_name'])} reposted:</p>''')

        if entry.get('reply') and entry['reply'].get('parent') and entry['reply']['parent'].get('author'):
            html_parts.append(f'''<details><summary><a href="{uri_to_https(entry['reply']['parent']['uri'])}">In reply to</a> <img src="{entry['reply']['parent']['author']['avatar']}" width=16 height=16> {html.escape(entry['reply']['parent']['author']['display_name'])}</summary><blockquote>{post_to_html(entry['reply']['parent'], doc, line, state, url)}</blockquote></details>''')

        if entry.get('post'):
            html_parts.append(post_to_html(entry['post'], doc, line, state, url))

        if entry.get('labels'):
            for label in labels:
                if label.get('val') in ('sexual',):
                    html_parts.insert(0, f'''<details><summary>{label['val']}</summary>''')
                    html_parts.append('</details>')
                    break
    elif entry['py_type'] == 'app.bsky.feed.defs#postView':
        url = uri_to_https(entry['uri'])

        if entry.get('record'):
            html_parts.append(post_to_html(entry['record'], doc, line, state, url))

        if entry.get('embed'):
            html_parts.append(post_to_html(entry['embed'], doc, line, state, url))
    elif entry['py_type'] == 'app.bsky.feed.post':
        if entry.get('text'):
            html_parts.append(f'''<p style="white-space: pre-wrap;">{html.escape(entry['text'])}</p>''')
    elif entry['py_type'] == 'app.bsky.embed.record#viewRecord':
        url = uri_to_https(entry['uri'])

        if entry.get('value'):
            html_parts.append(f'''<p><a href="{uri_to_https(entry['uri'])}">Embedded post</a> by <img src="{entry['author']['avatar']}" width=32 height=32> {html.escape(entry['author']['display_name'])}</p>''')
            html_parts.append(f'''<blockquote style="white-space: pre-wrap;">{post_to_html(entry['value'], doc, line, state, url)}</blockquote>''')
    elif entry['py_type'] == 'app.bsky.embed.images#view':
        for image in entry['images']:
            html_parts.append(post_to_html(image, doc, line, state, url))
    elif entry['py_type'] == 'app.bsky.embed.images#viewImage':
        html_parts.append(f'''<p><a href="{entry['fullsize']}"><img src="{entry['thumb']}"></a></p>''')

        if entry.get('alt'):
            html_parts.append(f'''<p style="white-space: pre-wrap;">Image description: {html.escape(entry['alt'])}</p>''')
    elif entry['py_type'] == 'app.bsky.embed.record#view':
        html_parts.append(post_to_html(entry['record'], doc, line, state, url))
    elif entry['py_type'] == 'app.bsky.embed.external#view':
        html_parts.append(post_to_html(entry['external'], doc, line, state, url))
    elif entry['py_type'] == 'app.bsky.embed.external#viewExternal':
        html_parts.append(f'''<p><a href="{entry['uri']}">{html.escape(entry.get('title', 'Link embed:'))}</a></p>''')
        if entry.get('thumb'):
            html_parts.append(f'''<p><img src="{entry['thumb']}"></p>''')
        if entry.get('description'):
            html_parts.append(f'''<p style="white-space: pre-wrap;">Description: {html.escape(entry['description'])}</p>''')
    elif entry['py_type'] == 'app.bsky.embed.recordWithMedia#view':
        html_parts.append(post_to_html(entry['record'], doc, line, state, url))
        html_parts.append(post_to_html(entry['media'], doc, line, state, url))
    elif entry['py_type'] == 'app.bsky.embed.video#view':
        # can't embed an m3u8 with pure HTML, so just put in the video thumbnail
        html_parts.append('<p>[video]</p>')
        html_parts.append(f'''<p><a href="{url}"><img src="{entry['thumbnail']}"></a></p>''')
    else:
        print(f"Unknown bluesky object type: {entry['py_type']}")

    return '\n'.join(html_parts)

def translate_entry(entry, doc, line, state):
    if entry['py_type'] == 'app.bsky.feed.defs#feedViewPost':
        post = entry['post']
        entry['fm:link'] = uri_to_https(post['uri'])
        entry['fm:author'] = post['author']['display_name']
        entry['fm:avatar'] = post['author']['avatar']
        entry['fm:timestamp'] = post['record']['created_at']
        entry['fm:html'] = post_to_html(entry, doc, line, state, entry['fm:link'])
    elif entry['py_type'] == 'app.bsky.notification.listNotifications#notification':
        entry['fm:author'] = entry['author']['display_name']
        entry['fm:avatar'] = entry['author']['avatar']
        entry['fm:timestamp'] = entry['indexed_at']
        reason = entry['reason']
        if reason == 'follow':
            entry['fm:title'] = "Followed you"
        elif reason == 'like':
            entry['fm:title'] = "Liked your post"
        elif reason == 'repost':
            entry['fm:title'] = "Reposted your post"
        elif reason == 'mention':
            entry['fm:title'] = "Mentioned you"
        elif reason == 'reply':
            entry['fm:title'] = "Replied to your post"
        elif reason == 'quote':
            entry['fm:title'] = "Quoted your post"
        else:
            entry['fm:title'] = f"Bluesky notification: {reason}"
        if entry.get('reason_subject'):
            entry['fm:link'] = uri_to_https(entry['reason_subject'])
        else:
            entry['fm:link'] = f'https://bsky.app/profile/{entry['author']['handle']}'
        #if entry.get('record'): # none of these have enough information to display, and I don't want to make an extra query
        #    entry['fm:html'] = post_to_html(entry['record'], doc, line, state, entry['fm:link'])
    else:
        print(f"Unknown bluesky entry type: {entry['py_type']}")

def get_indexed_at(entry):
    if entry.get('reason'):
        return entry['reason']['indexed_at']
    return entry['post']['indexed_at']

def process_timeline(line, state):
    client = get_client(state)

    prev_last_indexed = state.get(('bluesky', 'last_indexed'))
    new_last_indexed = None

    j = to_json(client.get_timeline())

    if j.get('feed'):
        new_last_indexed = get_indexed_at(j['feed'][0])

        if prev_last_indexed:
            response = j
            while get_indexed_at(j['feed'][-1]) > prev_last_indexed and response.get('cursor'):
                response = to_json(client.get_timeline(cursor = response['cursor']))
                if response['feed']:
                    j['feed'].extend(response['feed'])
                else:
                    break
            while j['feed'] and get_indexed_at(j['feed'][-1]) <= prev_last_indexed:
                j['feed'].pop(-1)

    j['fm:entries'] = j['feed']

    for entry in j['fm:entries']:
        translate_entry(entry, j, line, state)

    state['bluesky', 'last_indexed'] = new_last_indexed

    return core.JSON, j

def process_notifications(line, state):
    client = get_client(state)

    prev_last_indexed = state.get(('bluesky-notifications', 'last_indexed'))
    new_last_indexed = None

    j = to_json(client.app.bsky.notification.list_notifications())

    if j.get('notifications'):
        new_last_indexed = j['notifications'][0]['indexed_at']

        if prev_last_indexed:
            response = j
            while j['notifications'][0]['indexed_at'] > prev_last_indexed and response.get('cursor'):
                response = to_json(client.app.bsky.notification.list_notifications(cursor = response['cursor']))
                if response['notifications']:
                    j['notifications'].extend(response['notifications'])
                else:
                    break
            while j['notifications'] and j['notifications'][-1]['indexed_at'] <= prev_last_indexed:
                j['notifications'].pop(-1)

    j['fm:entries'] = j['notifications']
    for entry in j['fm:entries']:
        translate_entry(entry, j, line, state)

    state['bluesky-notifications', 'last_indexed'] = new_last_indexed

    return core.JSON, j

def process(line, state):
    if line.startswith('bluesky:'):
        return process_timeline(line, state)
    elif line.startswith('bluesky-notifications:'):
        return process_notifications(line, state)

