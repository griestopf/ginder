import requests
from github import Github
from github import Auth
from ginder_secrets import ginder_token

# g = Github(login_or_token=user_token)
auth=Auth.Token(ginder_token)
g = Github(auth=auth)
user = g.get_user()
print(user.raw_data)
repo = user.get_repo('FromFreeDeeTest')

print(repo.has_pages)


headers = {
    "Accept"                :  "application/vnd.github+json",
    "Authorization"         : f"Bearer {ginder_token}",
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
#curl -L -X POST -H "Accept: application/vnd.github+json" -H "Authorization: Bearer TOKEN" -H "X-GitHub-Api-Version: 2022-11-28" https://api.github.com/repos/griestopf/FromFreeDeeTest/pages -d '{"build_type":"workflow", "source":{"branch":"main","path":"/docs"}}'
print(res.json)

g.close()
