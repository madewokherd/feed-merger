#!/usr/bin/env python

import os
import readline
import sys
import traceback

descfilename = sys.argv[1]
output_filename = sys.argv[2]

with open('feed-merger-state') as f:
    state = eval(f.read())

items = []

def process_file(descfilename):
    with open(descfilename) as f:
        for line in f:
            try:
                line = line.strip()
                if line.startswith('mastodon:'):
                    import mastodon
                    mastodon.process(line, state, items)
                elif line.startswith('gmail:'):
                    import gmail
                    gmail.process(line, state, items)
                elif line.startswith('nebula:'):
                    import nebula
                    nebula.process(line, state, items)
                elif line.startswith('include:'):
                    process_file(line.split(':', 1)[1])
                else:
                    print(line)
            except:
                print("Failed processing line: ", line)
                traceback.print_exc()

process_file(descfilename)

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

