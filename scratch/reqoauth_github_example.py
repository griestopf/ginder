# Taken from https://requests-oauthlib.readthedocs.io/en/latest/examples/github.html

# Credentials you get from registering a new application
client_id = '02629493e33bb2d1dcf3'
# client_secret = <a hard coded secret - wow OAuth2 designers, you really suck>

# OAuth endpoints given in the GitHub API documentation
authorization_base_url = 'https://github.com/login/oauth/authorize'
token_url = 'https://github.com/login/oauth/access_token'

from requests_oauthlib import OAuth2Session
github = OAuth2Session(client_id)

# Redirect user to GitHub for authorization
authorization_url, state = github.authorization_url(authorization_base_url)
print('Please go here and authorize,', authorization_url)

# Get the authorization verifier code from the callback url
redirect_response = input('Paste the full redirect URL here:')

# Fetch the access token
# See https://github.com/requests/requests-oauthlib/blob/master/requests_oauthlib/oauth2_session.py#L204
# github.fetch_token(token_url, client_secret=client_secret, code=<code_from_response>)
github.fetch_token(token_url, client_secret=client_secret,
        authorization_response=redirect_response)

# Fetch a protected resource, i.e. user profile
r = github.get('https://api.github.com/user')
print(r.content)