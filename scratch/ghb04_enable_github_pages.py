import requests
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
repo = user.get_repo('FromFreeDeeTest')

print(repo.has_pages)


headers = {
    "Accept"                :  "application/vnd.github+json",
    "Authorization"         : f"Bearer {ginder_secrets.ginder_token}",
    "X-GitHub-Api-Version"  :  "2022-11-28"
}
data = {
    "build_type"  : "workflow",
    "source"      : {
        "branch" :"main",
        "path":"/docs"
    }    
}
url = f'https://api.github.com/repos/{user.login}/{repo.name}/pages'
res = requests.post(url=url, headers=headers, json=data)
#curl -L -X POST -H "Accept: application/vnd.github+json" -H "Authorization: Bearer <TOKEN>" -H "X-GitHub-Api-Version: 2022-11-28" https://api.github.com/repos/griestopf/FromFreeDeeTest/pages -d '{"build_type":"workflow", "source":{"branch":"main","path":"/docs"}}'
print(res.json)

g.close()
