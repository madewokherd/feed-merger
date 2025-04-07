import json
import urllib.parse
import urllib.request

import core

from html import escape as e

def process(line, state, items):
    url = line.split(':', 1)[1] #remove nebula:

    since_timestamp = state.get(('nebula', url, 'since_timestamp'))

    page_url = url

    recent_timestamp = None

    result = None

    while True:
        j = json.load(urllib.request.urlopen(page_url))

        if result is None:
            result = j
            result['fm:entries'] = entries = []

        if recent_timestamp is None:
            recent_timestamp = j['results'][0]['published_at']

        for video in j['results']:
            if since_timestamp and since_timestamp >= video['published_at']:
                break

            entries.append(video)

            video['fm:text'] = video['description']
            video['fm:link'] = video['share_url']
            video['fm:author'] = video['channel_title']
            video['fm:timestamp'] = video['published_at']
            video['fm:avatar'] = video['images']['channel_avatar']['src']
            video['fm:thumbnail'] = video['images']['thumbnail']['src']
            video['fm:title'] = video['title']

        else:
            if not since_timestamp:
                break

            page_url = j['next']
            continue

        break

    del result['results']

    state[('nebula', url, 'since_timestamp')] = recent_timestamp or since_timestamp

    return core.JSON, result

