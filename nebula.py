import json
import urllib.parse
import urllib.request

from html import escape as e

def process(line, state, items):
    url = line.split(':', 1)[1] #remove nebula:

    since_timestamp = state.get(('nebula', url, 'since_timestamp'))

    page_url = url

    recent_timestamp = None

    while True:
        j = json.load(urllib.request.urlopen(page_url))

        if recent_timestamp is None:
            recent_timestamp = j['results'][0]['published_at']

        for video in j['results']:
            if since_timestamp and since_timestamp >= video['published_at']:
                break

            broken_description = e(video['description']).replace('\n', '<br>')

            items.append((f"""

<h1><a href="{video['share_url']}">{video['channel_title']} - {video['title']}</a> {video['published_at']} <a name="{video['slug']}" href="#{video['slug']}">[anchor]</a></h1>

<p>{broken_description}</p>

<p><img width=320 height=180 src="{video['images']['thumbnail']['src']}"></p>""", video['published_at']))

        else:
            if not since_timestamp:
                break

            page_url = j['next']
            continue

        break

    state[('nebula', url, 'since_timestamp')] = recent_timestamp or since_timestamp

