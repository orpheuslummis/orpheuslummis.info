"""
build orpheuslummis.info and provide local web server for drafts etc

DONE notes index
DONE links as links
TODO recursive
TODO file deletion
"""

import functools
import glob
import hashlib
import http.server
import json
import os
import shutil
import socketserver
import subprocess
import sys
import threading
import time

import fire
import pypandoc # requires pandoc in path

AWS_BUCKET = 'orpheuslummis.info'
AWS_DISTRIBUTION = 'E231Q4SGKH5GRS'
BUILD_DIR = './docs' # for github pages
HOST = 'localhost'
PORT = 8765
WATCH_INTERVAL = 1.0
INDEX_FNAME = '_index.md'

class Builder(object):
    def __call__(self) -> None:
        self.local_serve(continuous=True)

    def local_serve(self, continuous: bool = False) -> None:
        def httpweb():
            Handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=BUILD_DIR)
            socketserver.TCPServer.allow_reuse_address = True
            server = socketserver.TCPServer((HOST, PORT), Handler)
            with server:
                print(f'serving at http://{HOST}:{PORT}')
                server.serve_forever()
        threading.Thread(target=httpweb).start()
        if continuous:
            while True:
                try:
                    self.build()
                    time.sleep(WATCH_INTERVAL)
                except KeyboardInterrupt:
                    os._exit(777)
        else:
            self.build()
    
    def build(self) -> None:
        os.makedirs(BUILD_DIR, exist_ok=True)
        os.makedirs(BUILD_DIR+'/notes/', exist_ok=True)
        shutil.copytree('static/', BUILD_DIR+'/static/', dirs_exist_ok=True)
        shutil.copytree('media/', BUILD_DIR+'/media/', dirs_exist_ok=True)
        phash_file = BUILD_DIR + '/phashes.json'

        # load stored phashes
        try:
            with open(phash_file, 'rb') as f:
                previous_phashes = json.load(f)
        except FileNotFoundError:
            previous_phashes = {}

        # compute current phashes
        files = glob.glob('./notes/*.md')
        files.append(f"./{INDEX_FNAME}")
        phashes = {}
        for path in files:
            with open(path, 'rb') as f:
                phashes[path] = hashlib.sha256(f.read()).hexdigest()

        # find changed/new hashes
        phashes_diff = {}
        for ph in phashes:
            if phashes[ph] not in previous_phashes.values():
                phashes_diff[ph] = phashes[ph]

        # compile the change/new files
        for path in phashes_diff:
            out_path = f'{BUILD_DIR}{path[1:][:-3]}.html'
            if path == f"./{INDEX_FNAME}":
                print("INDEX")
                out_path = f'{BUILD_DIR}/index.html'
                template_type = 'index'
            else:
                template_type = 'note'
            print(f'http://{HOST}:{PORT}{path[1:][:-3]}.html')
            pypandoc.convert_file(path,
                format='markdown+autolink_bare_uris+lists_without_preceding_blankline',
                to='html', outputfile=out_path,
                extra_args=[
                    f'--template=templates/{template_type}.html',
                    '--lua-filter=links-to-html.lua',
                ])

        # store the new hashes
        with open(phash_file, 'w') as f:
            json.dump(phashes, f)

    def publish(self) -> None:
        self.build()
        try:
            retcode = subprocess.call(f'aws s3 sync _build s3://{AWS_BUCKET}/ --delete --exclude "*.git/*"', shell=True)
            if retcode < 0:
                print("Child was terminated by signal", -retcode, file=sys.stderr)
        except OSError as e:
            print("Execution failed:", e, file=sys.stderr)
        try:
            retcode = subprocess.call(f"aws cloudfront create-invalidation --distribution-id {AWS_DISTRIBUTION} --paths '/*'", shell=True)
            if retcode < 0:
                print("Child was terminated by signal", -retcode, file=sys.stderr)
            else:
                print(f"https://{AWS_BUCKET}/index.html")
                print(f"https://{AWS_BUCKET}/notes/index.html")
        except OSError as e:
            print("Execution failed:", e, file=sys.stderr)

    def deploy(self) -> None:
        self.publish()

    def clean(self) -> None:
        shutil.rmtree(BUILD_DIR)

    def _build_portal(self) -> None:
        # create a notes index
        # TODO use latest last-update time from notes
        md = \
f'''
---
title: Notes index
status: generated
---

'''
        notes = sorted([(n.lower(), n) for n in glob.glob('./notes/*.md')])
        for _, n in notes:
            md = md + f'- [{n[8:][:-3]}]({n[8:][:-2]}html)\n'
        print("notes index") #FIXME
        pypandoc.convert_text(md, format='markdown+autolink_bare_uris', to='html', outputfile=f'{BUILD_DIR}/notes/index.html', extra_args=[f"--template=./templates/note.html"])


if __name__ == "__main__":
    fire.Fire(Builder())