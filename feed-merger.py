#!/usr/bin/env python

import datetime
import html
import html.parser
import json
import os
import os.path
import readline
import sys
import traceback

import core

entry_template = """<h1><a name="item{e['fm:counter']}"></a><?if e.get('fm:link')><a href="{e['fm:link']}"><?endif>{' - '.join(x for x in (e.get('fm:feedname') or f.get('fm:title'), e.get('fm:author'), e.get('fm:title')) if x)}<?if e.get('fm:link')></a><?endif> {e['fm:timestamp']} <a href="#item{e['fm:counter']}">[anchor]</a></h1>

<?if e.get('fm:html')><?html {translate_html(f, e, e['fm:html'])}><?endif>
"""

class HtmlTemplateFiller(html.parser.HTMLParser):
    def __init__(self, locals_dict):
        super().__init__()
        self.locals_dict = locals_dict
        self.strs = []
        self.stack = []
        self.output_enabled = True

    def get_contents(self):
        return ''.join(self.strs)

    def handle_starttag(self, tag, attrs, close=False):
        if not self.output_enabled:
            return

        self.strs.append('<')
        self.strs.append(tag)

        for (key, value) in attrs:
            self.strs.append(' ')
            self.strs.append(key)
            self.strs.append('="')
            self.strs.append(html.escape(str(eval(f'f"""{value}"""', globals(), self.locals_dict))))
            self.strs.append('"')

        if close:
            self.strs.append('/>')
        else:
            self.strs.append('>')

    def handle_endtag(self, tag):
        if not self.output_enabled:
            return

        self.strs.append('</')
        self.strs.append(tag)
        self.strs.append('>')

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs, close=True)

    def handle_data(self, data):
        if not self.output_enabled:
            return

        self.strs.append(html.escape(str(eval(f'f"""{data}"""', globals(), self.locals_dict))))

    def handle_pi(self, data):
        if ' ' in data:
            name, rest = data.split(' ', 1)
        else:
            name = data
            rest = ''

        if name == 'if':
            self.stack.append(('if', self.output_enabled))
            if self.output_enabled:
                self.output_enabled = bool(eval(rest, globals(), self.locals_dict))
        elif name == 'endif':
            name, output_enabled = self.stack.pop()
            if name != 'if':
                raise Exception("template has <?endif> without <?if>")
            self.output_enabled = output_enabled
        elif name == 'html':
            if not self.output_enabled:
                return

            self.strs.append(str(eval(f'f"""{rest}"""', locals=self.locals_dict)))
        else:
            raise Exception(f"template has unknown processing instruction {name}")

def items_from_json(j, items):
    if 'fm:entries' in j:
        for entry in j['fm:entries']:
            template_filler = HtmlTemplateFiller({
                'e': entry,
                'f': j,
            })
            template_filler.feed(entry_template)
            template_filler.close()

            items.append((template_filler.get_contents(), entry['fm:timestamp']))

def translate_html(feed, entry, data):
    # FIXME: handle base, tag filtering, and removal of <html> and <head> tags properly
    if '<body' in data:
        data = data.split('<body', 1)[1].split('>', 1)[-1]
    if '</body>' in data:
        data = data.split('</body>', 1)[0]
    return data

def handle_line(line):
    if line.startswith('mastodon:'):
        import mastodon
        mastodon.process(line, state, items)
        return core.SUCCESS, None
    elif line.startswith('gmail:'):
        import gmail
        gmail.process(line, state, items)
        return core.SUCCESS, None
    elif line.startswith('nebula:'):
        import nebula
        nebula.process(line, state, items)
        return core.SUCCESS, None
    elif line.startswith('github-branch:'):
        import github
        github.process(line, state, items)
        return core.SUCCESS, None
    elif line.startswith('gitlab-branch:'):
        import gitlab
        gitlab.process(line, state, items)
        return core.SUCCESS, None
    elif line.startswith('rss:'):
        import rss
        rss.process(line, state, items)
        return core.SUCCESS, None
    elif line.startswith('reddit:'):
        import reddit
        reddit.process(line, state, items)
        return core.SUCCESS, None
    elif line.startswith('include:'):
        process_file(line.split(':', 1)[1])
        return core.SUCCESS, None
    elif line.startswith(('http:', 'https:')):
        import web
        return web.process(line, state)
    elif line.endswith('.txt'):
        process_file(line)
        return core.SUCCESS, None
    else:
        raise NotImplementedError

item_counter = 0

def add_defaults(line, j):
    for entry in j['fm:entries']:
        if 'fm:title' not in entry:
            entry['fm:title'] = line
        if 'fm:timestamp' not in entry:
            entry['fm:timestamp'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if 'fm:id' not in entry and 'fm:link' in entry:
            entry['fm:id'] = entry['fm:link']
        global item_counter
        item_counter += 1
        entry['fm:counter'] = item_counter

def process_line(line):
    disposition, data = handle_line(line)
    while disposition == core.REDIRECT:
        disposition, data = handle_line(data)
    if disposition == core.JSON:
        add_defaults(line, data)
        items_from_json(data, items)
    elif disposition != core.SUCCESS:
        raise Exception("unrecognized disposition")

def process_file(descfilename):
    with open(descfilename) as f:
        for line in f:
            try:
                line = line.strip()
                process_line(line)
            except:
                print("Failed processing line: ", line)
                traceback.print_exc()

descfilename = sys.argv[1]
output_filename = sys.argv[2]

items = []

if output_filename == 'debug':
    state = {}

    line = descfilename
    disposition, data = handle_line(line)
    while disposition == core.REDIRECT:
        print("redirected to", data)
        line = data
        disposition, data = handle_line(line)

    if disposition == core.SUCCESS:
        print("handler returned success")
    elif disposition == core.JSON:
        json.dump(data, sys.stdout, indent=2)
        add_defaults(line, data)
        print()
        print()
        items_from_json(data, items)

    print("stored data:", state)
    print()

    print('items:')
    for item in items:
        print(item[1], item[0])
else:
    try:
        with open('feed-merger-state') as f:
            state = eval(f.read())
    except FileNotFoundError:
        state = {}

    process_line(descfilename)

    items.sort(key = lambda i: i[1])

    with open(output_filename, 'w') as f:
        f.write(
        """<!DOCTYPE html>
        <html lang="en">
          <head>
            <meta charset="utf-8">
            <title>""")

        f.write(descfilename)

        f.write("""</title>
          </head>
          <body>
        """)

        for (item, timestamp) in items:
            f.write(item)

        f.write("</body></html>")

    state_str = repr(state)
    eval(state_str)

    with open('feed-merger-state.new', 'w') as f:
        f.write(state_str)

    os.replace('feed-merger-state.new', 'feed-merger-state')

