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

auth=Auth.Token(ginder_secrets.ginder_token)
g = Github(auth=auth)
user = g.get_user()
print(user.raw_data)
freedee = user.get_repo('FreeDee')
print(freedee.raw_data)

g.close()
