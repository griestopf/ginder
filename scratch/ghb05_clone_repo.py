import os
import sys
import pygit2
from github import Github
from github import Auth
from ginder_secrets import ginder_token

# The local directory to clone the newly created repository to
local_dir = 'c:/temp/gindertest'


def shell_open(url):
    if sys.platform == "win32":
        os.startfile(url)
    else:
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.call([opener, url])


class MyRemoteCallbacks(pygit2.RemoteCallbacks):

    def transfer_progress(self, stats):
        print(f'{stats.indexed_objects}/{stats.total_objects}')

# Login with token
auth=Auth.Token(ginder_token)
g = Github(auth=auth)

# Get the user for the token
user = g.get_user()

# Get the repo to use as template
presentation_repo = user.get_repo('FromFreeDeeTest')

credentials = pygit2.UserPass(ginder_token,'x-oauth-basic')

# callbacks=pygit2.RemoteCallbacks(credentials=credentials)
callbacks=MyRemoteCallbacks(credentials=credentials)

repoClone = pygit2.clone_repository(presentation_repo.clone_url, local_dir, callbacks=callbacks)

g.close()
