import os
import sys
import pygit2
from github import Github
from github import Auth

#region Goop needed to run script inside blender
import os
import sys
local_dir_path = ''
try:
    import bpy
    local_dir_path = os.path.dirname(bpy.data.filepath)
    sys.path.append(local_dir_path) # needed for imports from the same directory
    print(f'Running inside Blender file within "{local_dir_path}".')
except Exception as ex:
    local_dir_path = os.path.dirname(os.path.abspath(__file__))
    print(f'Not running inside Blender.\n')
#endregion

#region Get secrets needed by OAuth
try:
    import ginder_secrets
    print(f'ginder_token: {ginder_secrets.ginder_token}')
except Exception as ex:
    print('Error importing ginder_secrets from "' + local_dir_path + '".' + '\n', 
          'Make sure ginder_secrets.py exists and defines the global "ginder_client_secret" and "ginder_token" variables.\n')
    raise ex
#endregion


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
auth=Auth.Token(ginder_secrets.ginder_token)
g = Github(auth=auth)

# Get the user for the token
user = g.get_user()

# Get the repo to use as template
presentation_repo = user.get_repo('FromFreeDeeTest')

credentials = pygit2.UserPass(ginder_secrets.ginder_token,'x-oauth-basic')

# callbacks=pygit2.RemoteCallbacks(credentials=credentials)
callbacks=MyRemoteCallbacks(credentials=credentials)

repoClone = pygit2.clone_repository(presentation_repo.clone_url, local_dir, callbacks=callbacks)

g.close()
