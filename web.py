import datetime
import email.utils
import html.parser
import urllib.error
import urllib.parse
import urllib.request

import core

# token values:
STARTTAG = 'STARTTAG'
ENDTAG = 'ENDTAG'
DATA = 'DATA'
COMMENT = 'COMMENT'
DECL = 'DECL'
PI = 'PI'
UNKNOWN = 'UNKNOWN'

class HtmlTokenizer(html.parser.HTMLParser):
    def __init__(self, convert_charrefs=True):
        self.tokens = []
        super().__init__(convert_charrefs=convert_charrefs)

    def handle_starttag(self, tag, attrs):
        self.tokens.append((STARTTAG, tag, attrs))
    
    def handle_endtag(self, tag):
        self.tokens.append((ENDTAG, tag, False))

    def handle_startendtag(self, tag, attrs):
        self.tokens.append((STARTTAG, tag, attrs))
        self.tokens.append((ENDTAG, tag, True))

    def handle_data(self, data):
        self.tokens.append((DATA, data, None))

    def handle_comment(self, data):
        self.tokens.append((DATA, data, None))

    def handle_decl(self, decl):
        self.tokens.append((DECL, decl, None))

    def handle_pi(self, data):
        self.tokens.append((PI, data, None))

    def unknown_decl(self, data):
        self.tokens.append((UNKNOWN, data, None))

def handle_soundcloud(url, js, state, data, data_str, tokens):
    if 'html:meta:property:twitter:app:url:googleplay' in js and \
        js['html:meta:property:twitter:app:url:googleplay'].startswith('soundcloud://users:'):
        # User page
        js['fm:author'] = js['html:meta:property:twitter:title']
        js['fm:entries'] = entries = []

        prev_mtime = state.get(('soundcloud', url, 'latest_mtime'))

        new_mtime = None

        found_any = False

        for i in range(len(tokens)):
            if tokens[i][0] == STARTTAG and tokens[i][1] == 'article' and dict(tokens[i][2]).get('class') == 'audible':
                entry = {}
                found_any = True
                entry['fm:author'] = js['fm:author']
                j = i + 1

                while not (tokens[j][0] == ENDTAG and tokens[j][1] == 'article'):
                    if tokens[j][0] == STARTTAG and tokens[j][1] == 'a' and dict(tokens[j][2]).get('itemprop') == 'url':
                        entry['fm:link'] = urllib.parse.urljoin(url, dict(tokens[j][2])['href'])
                        j += 1
                        if tokens[j][0] == DATA:
                            entry['fm:title'] = tokens[j][1]
                            j += 1
                    elif tokens[j][0] == STARTTAG and tokens[j][1] == 'time' and 'pubdate' in dict(tokens[j][2]):
                        j += 1
                        if tokens[j][0] == DATA:
                            entry['fm:timestamp'] = tokens[j][1]
                            j += 1
                    elif tokens[j][0] == STARTTAG and tokens[j][1] == 'meta' and dict(tokens[j][2]).get('itemprop') == 'duration':
                        entry['duration'] = dict(tokens[j][2]).get('content')
                        j += 1
                    else:
                        j += 1

                if prev_mtime and entry['fm:timestamp'] <= prev_mtime:
                    continue

                entry_html_json, entry_tokens = fetch_html(entry['fm:link'])
                entry.update(entry_html_json)
                entry['fm:text'] = entry_html_json['html:meta:itemprop:description']

                if new_mtime is None or new_mtime < entry['fm:timestamp']:
                    new_mtime = entry['fm:timestamp']

                entries.append(entry)

        if not found_any:
            raise Exception("Didn't find any uploads")

        state['soundcloud', url, 'latest_mtime'] = new_mtime or prev_mtime
        return core.JSON, js

    return core.UNHANDLED, None

def handle_soundgasm(url, js, state, data, data_str, tokens):
    import agegate
    agegate.check(state)

    parsed_url = urllib.parse.urlparse(url)
    if parsed_url.path.startswith('/u/') and parsed_url.path.strip('/').count('/') == 1:
        # User page
        js['fm:author'] = parsed_url.path.strip('/').split('/')[1]
        js['fm:entries'] = entries = []

        prev_mtime = state.get(('soundgasm', url, 'latest_mtime'))
        prev_url = state.get(('soundgasm', url, 'latest_url'))

        new_mtime = None
        new_url = None

        found_any = False

        for i in range(len(tokens)):
            if tokens[i][0] == STARTTAG and tokens[i][1] == 'div' and dict(tokens[i][2]).get('class') == 'sound-details':
                entry = {}
                found_any = True
                entry['fm:author'] = js['fm:author']
                j = i + 1

                # parse html data
                assert tokens[j][0] == STARTTAG and tokens[j][1] == 'a'
                entry['fm:link'] = urllib.parse.urljoin(url, dict(tokens[j][2])['href'])
                j += 1

                if entry['fm:link'] == prev_url:
                    break

                new_url = entry['fm:link']

                assert tokens[j][0] == DATA and tokens[j][1].strip()
                entry['fm:title'] = tokens[j][1]
                j += 1

                while not (tokens[j][0] == ENDTAG and tokens[j][1] == 'div'):
                    if tokens[j][0] == STARTTAG and tokens[j][1] == 'span' and dict(tokens[j][2]).get('class') == 'soundDescription':
                        j += 1
                        if tokens[j][0] == DATA:
                            if tokens[j][1].strip():
                                entry['fm:text'] = tokens[j][1]
                            j += 1
                    elif tokens[j][0] == STARTTAG and tokens[j][1] == 'span' and dict(tokens[j][2]).get('class') == 'playCount':
                        j += 1

                        assert tokens[j][0] == DATA and tokens[j][1].strip()
                        entry['play_count'] = int(tokens[j][1].rsplit(' ', 1)[-1])
                        j += 1
                    else:
                        j += 1

                entry_html = urllib.request.urlopen(entry['fm:link']).read().decode('utf-8')

                entry['media_url'] = entry_html.split('            m4a: "', 1)[1].split('"', 1)[0]

                req = urllib.request.Request(entry['media_url'], method='HEAD', headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0',
                })
                html_mtime = urllib.request.urlopen(req).headers['Last-Modified']
                entry['fm:timestamp'] = email.utils.parsedate_to_datetime(html_mtime).isoformat()

                if prev_mtime and entry['fm:timestamp'] <= prev_mtime:
                    break

                if new_mtime is None:
                    new_mtime = entry['fm:timestamp']

                entries.append(entry)
        
                if not prev_mtime:
                    break

        if not found_any:
            raise Exception("Didn't find any uploads")

        state['soundgasm', url, 'latest_mtime'] = new_mtime or prev_mtime
        state['soundgasm', url, 'latest_url'] = new_url or prev_url
        return core.JSON, js

    return core.UNHANDLED, None

def handle_ondisneyplus(url, js, state, data, data_str, tokens):
    entries = []
    current_entry = {}

    prev_slugs = set(state.get(('ondisneyplus', url, 'slugs'), []))

    for i in range(len(tokens)):
        if tokens[i][0] == STARTTAG:
            attrs = dict(tokens[i][2])
            if tokens[i][1] == 'div' and 'building-block' in attrs.get('class', '').split():
                if current_entry:
                    entries.append(current_entry)
                    current_entry = {}
            elif tokens[i][1] == 'a' and 'data-anchor-name' in attrs:
                current_entry['fm:link'] = urllib.parse.urljoin(url, attrs['href'])
                current_entry['data-slug'] = attrs['data-slug']
                current_entry['data-anchor-name'] = attrs['data-anchor-name']
            elif tokens[i][1] == 'img' and 'thumb' in attrs.get('class', '').split() and 'data-src' in attrs:
                current_entry['fm:thumbnail'] = urllib.parse.urljoin(url, attrs['data-src'])
                current_entry['fm:title'] = attrs['alt']
            elif tokens[i][1] == 'p' and attrs.get('class') == 'desc' and tokens[i+1][0] == DATA:
                current_entry['fm:text'] = tokens[i+1][1]

    if current_entry:
        entries.append(current_entry)

    if not entries:
        return core.UNHANDLED, None

    new_slugs = [entry['data-slug'] for entry in entries]

    entries = [entry for entry in entries if entry['data-slug'] not in prev_slugs]

    if not entries:
        return core.SUCCESS, None

    state['ondisneyplus', url, 'slugs'] = new_slugs
    js['fm:entries'] = entries

    return core.JSON, js

def handle_mcstories(url, js, state, data, data_str, tokens):
    import agegate
    agegate.check(state)

    parsed_url = urllib.parse.urlparse(url)
    if parsed_url.path.startswith('/Authors/') and 'html:meta:name:dcterms.creator' in js:
        # Author page
        js['fm:author'] = js['html:meta:name:dcterms.creator']
        js['fm:entries'] = entries = []

        prev_latest = state.get(('mcstories', url, 'latest'))

        new_latest = None

        found_any = False

        for i in range(len(tokens)):
            if tokens[i][0] == STARTTAG and tokens[i][1] == 'tr' and \
                tokens[i+1][0] == STARTTAG and tokens[i+1][1] == 'td':
                entry = {}
                found_any = True
                entry['fm:author'] = js['fm:author']
                j = i+2
                td = 0
                in_cite = False
                while not (tokens[j][0] == ENDTAG and tokens[j][1] == 'tr'):
                    if tokens[j][0] == STARTTAG and tokens[j][1] == 'td':
                        td += 1
                    elif tokens[j][0] == STARTTAG and tokens[j][1] == 'a':
                        entry['fm:link'] = urllib.parse.urljoin(url, dict(tokens[j][2])['href'])
                    elif tokens[j][0] == STARTTAG and tokens[j][1] == 'cite':
                        in_cite = True
                    elif tokens[j][0] == DATA and tokens[j][1].strip():
                        if td == 0 and in_cite:
                            entry['fm:title'] = tokens[j][1]
                            in_cite = False
                        elif td == 1:
                            entry['codes'] = tokens[j][1]
                        elif td == 2:
                            entry['ctime'] = tokens[j][1]
                        elif td == 3:
                            entry['mtime'] = tokens[j][1]
                    j += 1

                entry_ts = entry.get('mtime', entry['ctime'])
                entry_ts = datetime.datetime.strptime(entry_ts, '%d %b %Y').isoformat()

                if prev_latest and entry_ts <= prev_latest:
                    continue

                if not new_latest or new_latest < entry_ts:
                    new_latest = entry_ts

                entry['fm:timestamp'] = entry_ts

                if prev_latest:
                    entry_html_json, entry_tokens = fetch_html(entry['fm:link'])
                    entry['fm:timestamp'] = entry_html_json['http:mtime_iso']
                    entry['fm:text'] = entry_html_json['html:meta:name:dcterms.description']

                entries.append(entry)

        if not found_any:
            raise Exception("Didn't find any stories")

        state['mcstories', url, 'latest'] = new_latest or prev_latest
        return core.JSON, js

    return core.UNHANDLED, None

url_host_handlers = {
    'com': {
        'codeweavers': {
            'www': 'codeweavers.process',
        },
    },
}

html_host_handlers = {
    'com': {
        'disney': {
            'ondisneyplus': handle_ondisneyplus,
        },
        'mcstories': handle_mcstories,
        'soundcloud': handle_soundcloud,
    },
    'net': {
        'soundgasm': handle_soundgasm,
    },
}

def find_host_handler(url, host_handlers):
    for segment in urllib.parse.urlparse(url).hostname.split('.')[::-1]:
        if segment not in host_handlers:
            return None
        host_handlers = host_handlers[segment]
        if isinstance(host_handlers, str):
            module, fn = host_handlers.rsplit('.', 1)
            return getattr(__import__(module), fn)
        if not isinstance(host_handlers, dict):
            return host_handlers

def handle_html(url, js, state, data, data_str, tokens, use_handlers=True):
    old_charset = js.get('http:charset', 'utf-8')

    # look for a charset declaration
    html_charset = None
    for i in range(len(tokens)):
        if tokens[i][0] == STARTTAG and tokens[i][1] == 'meta':
            attrs = dict(tokens[i][2])
            if 'charset' in attrs:
                html_charset = attrs['charset']
                break
            if 'http-equiv' in attrs and attrs.get('http-equiv').lower() == 'content-type' and \
                'content' in attrs and 'charset=' in attrs['content'].lower():
                html_charset = attrs['content'].lower().split('charset=', 1)[1].split(';', 1)[0]
                break

    if html_charset and html_charset != old_charset:
        data_str = data.decode(html_charset, errors='replace')
        parser = HtmlTokenizer()
        parser.feed(data_str)
        tokens = parser.tokens

    for i in range(len(tokens)):
        if tokens[i][0] == STARTTAG and tokens[i][1] == 'meta':
            attrs = dict(tokens[i][2])
            if 'name' in attrs and 'content' in attrs:
                js[f'html:meta:name:{attrs["name"].lower()}'] = attrs['content']
            elif 'http-equiv' in attrs and 'content' in attrs:
                js[f'html:meta:http-equiv:{attrs["http-equiv"].lower()}'] = attrs['content']
            elif 'charset' in attrs:
                js['html:meta:charset'] = attrs['charset']
            elif 'itemprop' in attrs and 'content' in attrs:
                js[f'html:meta:itemprop:{attrs["itemprop"].lower()}'] = attrs['content']
            elif 'property' in attrs and 'content' in attrs:
                js[f'html:meta:property:{attrs["property"].lower()}'] = attrs['content']
        elif tokens[i][0] == STARTTAG and tokens[i][1] == 'title':
            try:
                if tokens[i+1][0] == DATA:
                    js['html:title'] = tokens[i+1][1]
            except IndexError:
                pass

    if use_handlers:
        host_handler = find_host_handler(url, html_host_handlers)
        if host_handler:
            result = host_handler(url, js, state, data, data_str, tokens)
            if result[0] != core.UNHANDLED:
                return result

    # defaults:
    entry = {}
    js['fm:entries'] = [entry]

    if 'html:title' in js:
        entry['fm:title'] = js['html:title']

    if 'html:meta:name:author' in js:
        entry['fm:author'] = js['html:meta:name:author']

    entry['fm:html'] = data_str

    return core.JSON, js

def handle_mrss(entry):
    if 'media:group' in entry:
        entry.update(entry['media:group'])
    if 'media:title' in entry and 'fm:title' not in entry:
        title = entry['media:title']
        if isinstance(title, str):
            entry['fm:title'] = title
        elif title.get('inner'):
            if title.get('type', 'plain') == 'plain':
                entry['fm:title'] = title['inner']
            else:
                entry['fm:title'] = html.unescape(title['inner'])
    if 'media:description' in entry and 'fm:text' not in entry and 'fm:html' not in entry:
        desc = entry['media:description']
        if isinstance(desc, str):
            entry['fm:text'] = desc
        elif desc.get('inner'):
            if desc.get('type', 'plain') == 'plain':
                entry['fm:text'] = desc['inner']
            else:
                entry['fm:html'] = desc['inner']
    if 'media:thumbnail' in entry:
        thumbnail = entry['media:thumbnail']
        if isinstance(thumbnail, list):
            thumbnail = thumbnail[0]
        entry['fm:thumbnail'] = thumbnail['url']
    if 'media:content' in entry:
        if isinstance(entry['media:content'], list):
            contents = entry['media:content']
        else:
            contents = (entry['media:content'],)
        for content in contents:
            if content.get('medium') == 'image':
                entry['fm:thumbnail'] = content['url']
                break

def find_favicon(url):
    best_link = None
    best_size = -1
    try:
        tokens = get_page_tokens(url)
    except urllib.error.HTTPError:
        return None
    except urllib.error.URLError:
        return None
    for token in tokens:
        if token[0] == STARTTAG and token[1] == 'link':
            attrs = dict(token[2])
            if attrs.get('rel') in ("icon", "shortcut icon", "apple-touch-icon"):
                if 'sizes' in attrs:
                    if attrs['sizes'] == 'any':
                        this_size = "any"
                    else:
                        this_size = int(attrs['sizes'].split('x')[0])
                elif attrs['rel'] == 'apple-touch-icon':
                    this_size = 192
                else:
                    this_size = 16
                if this_size != "any" and this_size > best_size:
                    best_size = this_size
                    best_link = urllib.parse.urljoin(url, attrs['href'])
        if token[0] == STARTTAG and token[1] == 'meta':
            attrs = dict(token[2])
            if attrs.get('name') == 'parsely-image-url':
                # tumblr uses this for the user avatar, so prefer it
                return urllib.parse.urljoin(url, attrs['content'])
    return best_link # may be None

def get_author_info(url, author_name, is_author_link=False):
    result = {}
    tokens = get_page_tokens(url)
    classes = ('author', 'headshot', 'head_shot', 'contributor', 'avatar')
    for i in range(len(tokens)):
        if tokens[i][0] == STARTTAG and tokens[i][1] == 'a':
            num_indicators = 0
            attrs = dict(tokens[i][2])
            if attrs.get('href'):
                img_link = None
                if any(c in attrs['href'].lower() for c in classes):
                    num_indicators += 1
                if attrs.get('class') and any(c in attrs['class'].lower() for c in classes):
                    num_indicators += 1
                if i + 1 < len(tokens) and tokens[i+1][0] == DATA and author_name in tokens[i+1][1]:
                    num_indicators += 1
                if author_name.lower() in urllib.parse.unquote(attrs['href']).lower().replace('-', ' ').replace('_', ' ').replace('%20', ' '):
                    num_indicators += 1
                if i + 1 < len(tokens) and tokens[i+1][0] == STARTTAG and tokens[i+1][1] == 'img':
                    img_attrs = dict(tokens[i+1][2])
                    if 'class' in img_attrs and any(c in img_attrs['class'].lower() for c in classes):
                        num_indicators += 1
                    if 'src' in img_attrs:
                        img_link = urllib.parse.urljoin(url, img_attrs['src'])
                        if any(c in img_link.lower() for c in classes):
                            num_indicators += 1
                    if 'alt' in img_attrs and author_name in img_attrs['alt']:
                        num_indicators += 1
                if num_indicators >= 2:
                    result['fm:author_link'] = urllib.parse.urljoin(url, attrs['href'])
                    if img_link:
                        result['fm:author'] = img_link
                        break
        if tokens[i][0] == STARTTAG and tokens[i][1] == 'img':
            attrs = dict(tokens[i][2])
            if 'src' in attrs:
                num_indicators = 0
                link = urllib.parse.urljoin(url, attrs['src'])
                if any(c in link.lower() for c in classes):
                    num_indicators += 1
                if author_name.lower() in urllib.parse.unquote(link).lower().replace('-', ' ').replace('_', ' ').replace('%20', ' '):
                    num_indicators += 1
                if 'alt' in attrs and author_name in attrs['alt']:
                    num_indicators += 1
                if 'class' in attrs and any(c in attrs['class'].lower() for c in classes):
                    num_indicators += 1
                if num_indicators >= 2:
                    result['fm:avatar'] = link
                    break
        if tokens[i][0] == STARTTAG and tokens[i][1] == 'script' and tokens[i+1][0] == DATA and tokens[i+1][1].startswith('var initialData = ') and is_author_link:
            ytdata = json.loads(tokens[i+1][1][18:-1])
            result['fm:avatar'] = ytdata['header']['pageHeaderRenderer']['content']['pageHeaderViewModel']['image']['decoratedAvatarViewModel']['avatar']['avatarViewModel']['image']['sources'][-1]['url']
            break
        if tokens[i][0] == STARTTAG and tokens[i][1] == 'meta':
            attrs = dict(tokens[i][2])
            if attrs.get('property') == 'og:image' and attrs.get('content') and is_author_link:
                result['fm:avatar'] = urllib.parse.urljoin(url, attrs['content'])
                break

    return result

def find_avatars(js):
    authors = {}
    author_links = {}

    for entry in js.get('fm:entries', ()):
        if 'fm:avatar' not in entry:
            if 'fm:author' in entry and 'fm:link' in entry:
                author = entry['fm:author']
                if author in authors:
                    if authors[author]:
                        entry['fm:avatar'] = authors[author]
                    if author_links.get(author):
                        entry['fm:author_link'] = author_links[author]
                    continue

                if 'fm:author_link' not in entry and author.startswith(('http://', 'https://')):
                    entry['fm:author_link'] = author

                if 'fm:author_link' not in entry:
                    info = get_author_info(entry['fm:link'], author)
                    for key in info:
                        if key not in entry:    
                            entry[key] = info[key]

                    if 'fm:author_link' in info:
                        author_links[author] = info['fm:author_link']

                    if 'fm:avatar' in info:
                        authors[author] = info['fm:avatar']
                        continue

                if 'fm:author_link' in entry:
                    # search page for author avatar
                    info = get_author_info(entry['fm:author_link'], author, is_author_link=True)
                    for key in info:
                        if key not in entry:    
                            entry[key] = info[key]

                    if 'fm:avatar' in info:
                        authors[author] = info['fm:avatar']
                        continue

    if any('fm:avatar' not in x for x in js.get('fm:entries', ())) and js.get('fm:link'):
        if not js.get('fm:avatar'):
            favicon = find_favicon(js['fm:link'])
            if favicon:
                js['fm:avatar'] = favicon
        if js.get('fm:avatar'):
            for entry in js['fm:entries']:
                if 'fm:avatar' not in entry:
                    entry['fm:avatar'] = js['fm:avatar']

def handle_rss(url, js, state, data, data_str, tokens):
    prev_latest = state.get(('rss', url, 'latest'))

    new_latest = None

    stack = [('', js)] # tagname, dictionary

    # split this into dictionaries
    for (token_type, token_name, token_data) in tokens:
        if token_type == STARTTAG and token_name in ('rss', 'channel'):
            # ignore these tags
            continue

        if token_type == STARTTAG and token_name == 'item':
            entry = {}
            stack.append(('item', entry))
            if 'fm:entries' not in js:
                js['fm:entries'] = []
            js['fm:entries'].append(entry)
            continue

        if token_type == STARTTAG:
            stack.append((token_name, {key: value for key, value in token_data if not key.startswith('xmlns:')}))
            continue

        if token_type == DATA and token_name.strip():
            stack[-1][1]['inner'] = token_name
            continue

        if token_type == UNKNOWN and token_name.startswith('CDATA['):
            stack[-1][1]['inner'] = token_name[6:]
            continue

        if token_type == ENDTAG and any(x[0] == token_name for x in stack):
            while True:
                old_tag, old_dict = stack.pop()

                if old_tag != 'item':
                    if len(old_dict) == 1 and 'inner' in old_dict:
                        val = old_dict['inner']
                    else:
                        val = old_dict

                    parent_dict = stack[-1][1]

                    if old_tag in parent_dict:
                        if isinstance(parent_dict[old_tag], list):
                            parent_dict[old_tag].append(val)
                        else:
                            parent_dict[old_tag] = [parent_dict[old_tag], val]
                    else:
                        parent_dict[old_tag] = val

                if old_tag == token_name:
                    break
            continue

    if 'title' in js:
        js['fm:title'] = html.unescape(js['title'])

    if 'link' in js:
        js['fm:link'] = js['link']

    if 'icon' in js:
        js['fm:avatar'] = js['icon']

    for entry in js['fm:entries']:
        if 'link' in entry:
            entry['fm:link'] = entry['link']
        elif 'enclosure' in entry and 'url' in entry['enclosure']:
            entry['fm:link'] = entry['enclosure']['url']
        if 'title' in entry:
            entry['fm:title'] = html.unescape(entry['title'])
        if 'content:encoded' in entry:
            entry['fm:html'] = entry['content:encoded']
        elif 'description' in entry:
            entry['fm:html'] = entry['description']
        if 'author' in entry:
            entry['fm:author'] = entry['author']
        elif 'dc:creator' in entry:
            if isinstance(entry['dc:creator'], list):
                entry['fm:author'] = ', '.join(entry['dc:creator'])
            else:
                entry['fm:author'] = entry['dc:creator']
        if 'pubdate' in entry:
            entry['fm:timestamp'] = email.utils.parsedate_to_datetime(entry['pubdate']).isoformat()
        if 'icon' in entry:
            entry['fm:avatar'] = entry['icon']
        handle_mrss(entry)

    for i in range(len(js['fm:entries']) - 1, -1, -1):
        entry = js['fm:entries'][i]
        if 'fm:timestamp' in entry:
            ts = entry['fm:timestamp']
            if prev_latest and ts <= prev_latest:
                js['fm:entries'].pop(i)
                continue
            if not new_latest or ts > new_latest:
                new_latest = ts

    state['rss', url, 'latest'] = new_latest or prev_latest

    find_avatars(js)

    return core.JSON, js

def handle_atom(url, js, state, data, data_str, tokens):
    prev_latest = state.get(('atom', url, 'latest'))

    new_latest = None

    stack = [('', js)] # tagname, dictionary

    # split this into dictionaries
    for (token_type, token_name, token_data) in tokens:
        if token_type == STARTTAG and token_name in ('feed', 'channel'):
            # ignore these tags
            continue

        if token_type == STARTTAG and token_name == 'entry':
            entry = {}
            stack.append(('entry', entry))
            if 'fm:entries' not in js:
                js['fm:entries'] = []
            js['fm:entries'].append(entry)
            continue

        if 'fm:_inner_xml' in stack[-1][1]:
            inner = stack[-1][1]['fm:_inner_xml']
            if token_type == ENDTAG:
                if token_name == stack[-1][0]:
                    old_tag, old_dict = stack.pop()
                    old_dict['inner'] = ''.join(old_dict['fm:_inner_xml'])
                    del old_dict['fm:_inner_xml']

                    parent_dict = stack[-1][1]

                    if old_tag in parent_dict:
                        if isinstance(parent_dict[old_tag], list):
                            parent_dict[old_tag].append(old_dict)
                        else:
                            parent_dict[old_tag] = [parent_dict[old_tag], old_dict]
                    else:
                        parent_dict[old_tag] = old_dict
                else:
                    inner.append('</')
                    inner.append(token_name)
                    inner.append('>')
            elif token_type == STARTTAG:
                inner.append('<')
                inner.append(token_name)

                for (key, value) in token_data:
                    inner.append(' ')
                    inner.append(key)
                    inner.append('="')
                    inner.append(html.escape(value))
                    inner.append('"')

                inner.append('>')
            elif token_type == DATA or token_type == UNKNOWN:
                inner.append(token_name)
            continue

        if token_type == STARTTAG:
            stack.append((token_name, {key: value for key, value in token_data if not key.startswith('xmlns:')}))
            if stack[-1][1].get('type') == 'xhtml':
                stack[-1][1]['fm:_inner_xml'] = []
            continue

        if token_type == DATA and token_name.strip():
            stack[-1][1]['inner'] = token_name
            continue

        if token_type == UNKNOWN and token_name.startswith('CDATA['):
            stack[-1][1]['inner'] = token_name[6:]
            continue

        if token_type == ENDTAG and any(x[0] == token_name for x in stack):
            while True:
                old_tag, old_dict = stack.pop()

                if old_tag != 'item':
                    if len(old_dict) == 1 and 'inner' in old_dict:
                        val = old_dict['inner']
                    else:
                        val = old_dict

                    parent_dict = stack[-1][1]

                    if old_tag in parent_dict:
                        if isinstance(parent_dict[old_tag], list):
                            parent_dict[old_tag].append(val)
                        else:
                            parent_dict[old_tag] = [parent_dict[old_tag], val]
                    else:
                        parent_dict[old_tag] = val

                if old_tag == token_name:
                    break
            continue

    for entry in js.get('fm:entries', []) + [js]:
        if 'link' in entry:
            if isinstance(entry['link'], list):
                for item in entry['link']:
                    if item.get('rel', 'alternate') == 'alternate':
                        entry['fm:link'] = item['href']
            else:
                entry['fm:link'] = entry['link']['href']
        if 'title' in entry:
            if isinstance(entry['title'], str):
                entry['fm:title'] = entry['title']
            elif entry['title'].get('type', 'text') == 'text':
                entry['fm:title'] = entry['title']['inner']
            elif entry['title']['type'] == 'html':
                entry['fm:title'] = html.unescape(entry['title']['inner'])
        if 'content' in entry or 'summary' in entry:
            content = entry.get('content', entry.get('summary'))
            if content.get('type') == 'text':
                entry['fm:text'] = content.get('inner', '')
            else:
                entry['fm:html'] = content.get('inner', '')
                if 'xml:base' in content and entry is not js:
                    entry['fm:base'] = content['xml:base']
        if 'author' in entry:
            if 'name' in entry['author']:
                entry['fm:author'] = entry['author']['name']
            if 'uri' in entry['author']:
                entry['fm:author_link'] = entry['author']['uri']
        if 'published' in entry or 'updated' in entry:
            entry['fm:timestamp'] = datetime.datetime.fromisoformat(entry.get('published', entry.get('updated'))).astimezone(datetime.timezone.utc).isoformat()
        handle_mrss(entry)

    for i in range(len(js.get('fm:entries', ())) - 1, -1, -1):
        entry = js['fm:entries'][i]
        if 'fm:timestamp' in entry:
            ts = entry['fm:timestamp']
            if prev_latest and ts <= prev_latest:
                js['fm:entries'].pop(i)
                continue
            if not new_latest or ts > new_latest:
                new_latest = ts

    state['atom', url, 'latest'] = new_latest or prev_latest

    find_avatars(js)

    return core.JSON, js

def get_page_tokens(url):
    headers = {}
    headers['User-Agent'] = 'feed-merger/1.0 +https://github.com/madewokherd/feed-merger'
    js, headers, response = fetch_http(url, headers=headers)
    data = response.read()

    data_str = data.decode(js.get('http:charset', 'utf-8'), errors='replace')
    parser = HtmlTokenizer()
    parser.feed(data_str)

    return parser.tokens

def handle_sgml(url, js, state, response):
    data = response.read()

    data_str = data.decode(js.get('http:charset', 'utf-8'), errors='replace')
    parser = HtmlTokenizer()
    parser.feed(data_str)

    for token in parser.tokens:
        token_type, tag, tdata = token

        if token_type == DECL:
            tag, rest = tag.split(' ', 1)
            if tag.lower() == 'doctype':
                doctype = rest.split(' ', 1)[0]
                if doctype == 'html':
                    return handle_html(url, js, state, data, data_str, parser.tokens)
                else:
                    break
        elif token_type == STARTTAG:
            if tag == 'html':
                return handle_html(url, js, state, data, data_str, parser.tokens)
            elif tag == 'rss':
                return handle_rss(url, js, state, data, data_str, parser.tokens)
            elif tag == 'feed':
                return handle_atom(url, js, state, data, data_str, parser.tokens)
            else:
                break
        elif token_type == DATA and tag.strip():
            break

    if js.get('http:mimetype') in ('text/html', 'text/xhtml+xml'):
        return handle_html(url, js, state, data, data_str, parser.tokens)

    # Don't know how to parse this, just use the defaults
    js['fm:entries'] = [{}]
    return core.JSON, js

mimetype_handlers = {
    'text/html': handle_sgml,
    'text/xhtml+xml': handle_sgml,
    'text/xml': handle_sgml,
    'application/xml': handle_sgml,
    'application/atom+xml': handle_sgml,
    'application/rss+xml': handle_sgml,
}

def fetch_html(url, *args, **kwargs):
    # returns json, tokens
    js, headers, response = fetch_http(url, *args, **kwargs)

    data = response.read()
    data_str = data.decode('utf-8', errors='replace')
    parser = HtmlTokenizer()
    parser.feed(data_str)

    _disposition, js = handle_html(url, js, {}, data, data_str, parser.tokens, False)

    fill_http_defaults(js)

    return js, parser.tokens

def fetch_http(url, data=None, headers={}):
    # returns json, headers, response
    req = urllib.request.Request(url, data=data, headers=headers)

    try:
        response = urllib.request.urlopen(req)
    except urllib.error.HTTPError as e:
        if e.code == 304:
            return None, e.headers, e.fp
        raise

    j = {}
    # fill in http fields
    if 'http:headers' not in j:
        headers = {}
        for key, value in response.getheaders():
            key = key.lower()
            if key in headers:
                if isinstance(headers[key], list):
                    headers[key].append(value)
                else:
                    headers[key] = [headers[key], value]
            else:
                headers[key] = value
        j['http:headers'] = headers
    if 'http:url' not in j:
        j['http:url'] = url

    return j, response.headers, response

def fill_http_defaults(json):
    j = json
    if 'fm:base' not in j and 'http:url' in j:
        j['fm:base'] = j['http:url']

    if 'http:headers' in j:
        if "last-modified" in j['http:headers']:
            mtime_iso = email.utils.parsedate_to_datetime(j['http:headers']['last-modified']).isoformat()

            if 'http:mtime_iso' not in j:
                j['http:mtime_iso'] = mtime_iso

            if 'fm:entries' in j:
                for entry in j['fm:entries']:
                    if 'fm:timestamp' not in entry:
                        entry['fm:timestamp'] = mtime_iso

    if 'fm:entries' in j and 'http:url' in j:
        for entry in j['fm:entries']:
            if 'fm:link' not in entry:
                entry['fm:link'] = j['http:url']

def process(line, state):
    host_handler = find_host_handler(line, url_host_handlers)
    if host_handler:
        result = host_handler(line, state)
        if result[0] != core.UNHANDLED:
            return result

    etag = state.get(('web', line, 'etag'))
    mtime = state.get(('web', line, 'mtime'))

    headers = {}
    if etag:
        headers['If-None-Match'] = etag
    if mtime:
        headers['If-Modified-Since'] = mtime

    headers['User-Agent'] = 'feed-merger/1.0 +https://github.com/madewokherd/feed-merger'

    json, headers, response = fetch_http(line, headers=headers)
    if json is None:
        # 304 status
        return core.SUCCESS, None

    if 'content-type' in headers:
        ct = headers['content-type']
        if not isinstance(ct, list):
            ct = ct.lower()
            if 'boundary=' not in ct:
                json['http:mimetype'] = ct.split(';', 1)[0]
                if 'charset=' in ct:
                    json['http:charset'] = ct.split('charset=', 1)[1].split(';', 1)[0]

    if json.get('http:headers', {}).get('content-type', '').split(';', 1)[0].lower() in mimetype_handlers:
        result = mimetype_handlers[json['http:mimetype']](line, json, state, response)
    else:
        # Don't know how to parse this, just use the defaults
        result = core.JSON, json
        json['fm:entries'] = [{}]

    if result[0] == core.JSON:
        j = result[1]

        fill_http_defaults(j)

    state['web', line, 'etag'] = response.headers.get('ETag')
    state['web', line, 'mtime'] = response.headers.get('Last-Modified')

    return result
