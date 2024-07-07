#!/usr/bin/env python

import os
import os.path
import readline
import sys
import traceback

import core

PRINT_JSON = True

descfilename = sys.argv[1]
output_filename = sys.argv[2]

with open('feed-merger-state') as f:
    state = eval(f.read())

items = []

def process_line(line):
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
    else:
        raise NotImplementedError

def process_file(descfilename):
    with open(descfilename) as f:
        for line in f:
            try:
                line = line.strip()
                disposition, data = process_line(line)
                while disposition == core.REDIRECT:
                    disposition, data = process_line(line)
                if disposition == core.SUCCESS:
                    continue
                if disposition == core.JSON:
                    json.dump(data, sys.stdout, indent=2)
                else:
                    raise Exception("unrecognized disposition")
            except:
                print("Failed processing line: ", line)
                traceback.print_exc()

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

