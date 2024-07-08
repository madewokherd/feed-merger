import datetime
import email.utils
import html.parser
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

def fetch_http(url, data=None, headers=None):
    # returns json, headers, response
    req = urllib.request.Request(url, data=data, headers=headers)
    response = urllib.request.urlopen(req)

    if response.status == 304:
        return None, response.headers, response

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

    if 'http:headers' in j and "last-modified" in j['http:headers']:
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
    etag = state.get(('web', line, 'etag'))
    mtime = state.get(('web', line, 'mtime'))

    headers = {}
    if etag:
        headers['If-None-Match'] = etag
    if mtime:
        headers['If-Modified-Since'] = mtime

    json, headers, response = fetch_http(line, headers=headers)
    if json is None:
        # 304 status
        return core.SUCCESS, None

    # Don't know how to parse this, just use the defaults
    result = core.JSON, json
    json['fm:entries'] = [{}]

    if result[0] == core.JSON:
        j = result[1]

        fill_http_defaults(j)

    state['web', line, 'etag'] = response.headers.get('ETag')
    state['web', line, 'mtime'] = response.headers.get('Last-Modified')

    return result
