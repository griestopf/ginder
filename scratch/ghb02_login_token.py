import json
from github import Github
from github import Auth
from ginder_secrets import ginder_token

# g = Github(login_or_token=user_token)
auth=Auth.Token(ginder_token)
g = Github(auth=auth)
user = g.get_user()
print(user.raw_data)
freedee = user.get_repo('FreeDee')
print(freedee.raw_data)





g.close()
