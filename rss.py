import datetime

import feedparser

def process(line, state, items):
    url = line.split(':', 1)[1]

    etag = state.get(('rss', url, 'etag'))
    modified = state.get(('rss', url, 'modified'))
    latest_entry = state.get(('rss', url, 'latest_entry'))
    nodate_entries = state.get(('rss', url, 'nodate_entries'))

    new_latest = latest_entry
    new_nodate = set()

    d = feedparser.parse(url, etag=etag, modified=modified)

    if d.get('status') == 304:
        # no changes
        return

    for entry in d.entries:
        updated = entry.get('published_parsed') or entry.get('updated_parsed')
        if updated:
            if latest_entry and latest_entry >= updated:
                continue
            elif not new_latest or updated > new_latest:
                new_latest = updated
        else:
            id = entry.get('id')
            if id:
                new_nodate.add(id)
                if id in nodate_entries:
                    continue
            updated = entry.get('created_parsed') or d.get('modified_parsed') or datetime.utctimetuple()

        iso_date = datetime.datetime(updated[0], updated[1], updated[2], updated[3], updated[4], min(updated[5], 60), tzinfo=datetime.timezone.utc).isoformat()

        author_name = entry.get('author') or d.get('title') or d.get('author') or ''

        if author_name:
            author_name += ' - '

        if entry.get('id'):
            anchor = f'<a name="{entry.id}" href="#{entry.id}">[anchor]</a>'
        else:
            anchor = ''

        if entry.get('content'):
            c = entry.content[0]
            if 'text/plain' in c:
                content = '<p>' + e(c).replace('\n', '<br>') + '</p>'
            else:
                content = c
        elif entry.get('summary'):
            content = '<p>' + entry.get('summary') + '</p>'
        else:
            content = ''

        if 'media_thumbnail' in entry:
            thumbnail = entry['media_thumbnail']
            if 'url' in thumbnail:
                if 'width' in thumbnail and 'height' in thumbnail:
                    content = f"""<p><img src="{thumbnail['url']} width="{thumbnail['width']}" height="{thumbnail['height']}"></p>""" + content
                else:
                    content = f"""<p><img src="{thumbnail['url']}></p>""" + content

        items.append((f"""

<h1><a href="{entry.get("link")}">{author_name} {entry.get("title")}</a> {iso_date} {anchor}</h1>

{content}""", iso_date))

    state['rss', url, 'etag'] = d.get('etag')
    state['rss', url, 'modified'] = d.get('modified')
    if new_latest:
        new_latest = tuple(new_latest)
    state['rss', url, 'latest_entry'] = new_latest
    state['rss', url, 'nodate_entries'] = new_nodate
