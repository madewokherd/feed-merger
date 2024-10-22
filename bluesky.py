import getpass
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

def translate_entry(entry, doc, line, state):
    post = entry['post']
    parse = urllib.parse.urlparse(post['uri'])
    if parse.scheme != 'at':
        entry['fm:link'] = post['uri']
    else:
        did = parse.netloc
        collection, rkey = parse.path.lstrip('/').split('/', 1)
        if collection == 'app.bsky.feed.post':
            entry['fm:link'] = f'https://bsky.app/profile/{did}/post/{rkey}'
        else:
            entry['fm:link'] = post['uri']
    entry['fm:author'] = post['author']['display_name']
    entry['fm:timestamp'] = post['record']['created_at']
    entry['fm:text'] = post['record']['text']

def process_timeline(line, state):
    client = get_client(state)

    prev_last_indexed = state.get(('bluesky', 'last_indexed'))
    new_last_indexed = None

    j = to_json(client.get_timeline())

    if j.get('feed'):
        new_last_indexed = j['feed'][0]['post']['indexed_at']

        if prev_last_indexed:
            response = j
            while j['feed'][-1]['post']['indexed_at'] > prev_last_indexed and 'cursor' in response:
                response = client.get_timeline(cursor = response['cursor'])
                if response['feed']:
                    j['feed'].extend(response['feed'])
                else:
                    break
            while j['feed'] and j['feed'][-1]['post']['indexed_at'] <= prev_last_indexed:
                j['feed'].pop(-1)

    j['fm:entries'] = j['feed']

    for entry in j['fm:entries']:
        translate_entry(entry, j, line, state)

    state['bluesky', 'last_indexed'] = new_last_indexed

    return core.JSON, j

def process(line, state):
    if line.startswith('bluesky:'):
        return process_timeline(line, state)

