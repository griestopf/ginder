import json
import os
import sys
import requests
from requests_oauthlib import OAuth2Session
import pygit2
from github import Github
from github import Auth

# The token fetched after the ginder app was registered
user_token = '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'

# The local directory to clone the newly created repository to
local_dir = 'c:/temp/gindertest'


def shell_open(url):
    if sys.platform == "win32":
        os.startfile(url)
    else:
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.call([opener, url])

# Unfortunately GitHub pages settings on a repository are not covered by PyGitHub. 
# Thus wee need to call the REST API endpoint ourselves
def enable_github_pages_from_action(token : str, user_login : str, repo_name : str) -> str:
    headers = {
        "Accept"                :  "application/vnd.github+json",
        "Authorization"         : f"Bearer {token}",
        "X-GitHub-Api-Version"  :  "2022-11-28"
    }
    data = {
        "build_type"  : "workflow",
        "source"      : {
            "branch" :"main",
            "path":"/docs"
        }    
    }
    url = f'https://api.github.com/repos/{user_login}/{repo_name}/pages'
    res = requests.post(url=url, headers=headers, json=data)
    # {
    # "url": "https://api.github.com/repos/griestopf/FromFreeDeeTest/pages",
    # "status": null,
    # "cname": null,
    # "custom_404": false,
    # "html_url": "https://griestopf.github.io/FromFreeDeeTest/",
    # "build_type": "workflow",
    # "source": {
    #     "branch": "main",
    #     "path": "/"
    # },
    # "public": true,
    # "protected_domain_state": null,
    # "pending_domain_unverified_at": null,
    # "https_enforced": true
    # }    
    # TODO: check result
    if not (200 <= res.status_code and res.status_code < 300):
        raise Exception(f"Could not enable GitHub Pages on {repo_name} :\n {res.text}")
    return res.json()["html_url"]



# Login with token
auth=Auth.Token(user_token)
g = Github(auth=auth)

# Get the user for the token
user = g.get_user()

# Get the repo to use as template
template_repo = user.get_repo('FreeDee')

# Set-up the new presentation_repo using the template
presentation_repo = user.create_repo_from_template('FromFreeDeeTest', template_repo, description='For debugging purposes only', include_all_branches=False, private=False)

# Enable github page creation from action
page_url = enable_github_pages_from_action(user_token, user.login, presentation_repo.name)
shell_open(page_url)


# Modify readme (will also trigger page generation action)
contents = presentation_repo.get_contents("/README.md")
presentation_repo.update_file(contents.path, 'commit number one', '# FromFreeDeeTest\nRepo template to automatically generate browsable 3D contents from uploaded blender files', contents.sha)




g.close()
