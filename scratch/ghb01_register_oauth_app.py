import os
import sys
import logging
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
import urllib.parse
from requests_oauthlib import OAuth2Session

# Add this file's dir to the search path for imports (required for scripts running in blender).
local_dir_path = ''
try:
    import bpy
    local_dir_path = os.path.dirname(bpy.data.filepath)
    print(f'Running inside Blender file within "{local_dir_path}".')
    sys.path.append(local_dir_path)
except:
    local_dir_path = os.path.dirname(os.path.abspath(__file__))
    print(f'Not running inside Blender.')


try:
    from ginder_secrets import ginder_client_secret
except Exception as ex:
    print('Error importing ginder_secrets from "' + local_path + '".' + '\n', 
          'Make sure ginder_secrets.py exists and defines the global "ginder_client_secret" and "ginder_token" variables.\n')
    raise ex

def shell_open(url):
    if sys.platform == "win32":
        os.startfile(url)
    else:
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.call([opener, url])

# HTTP-Callback Handler inspired by
# https://gist.github.com/mdonkers/63e115cc0c79b4f6b8b3a6b797e485c7

class Oauth2CallbackHandler(BaseHTTPRequestHandler):
    code = ''
    
    def _set_response(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()

    def do_GET(self):
        logging.info("GET request,\nPath: %s\nHeaders:\n%s\n", str(self.path), str(self.headers))

        url_parts = urllib.parse.urlparse(self.path)
        query_parts = urllib.parse.parse_qs(url_parts.query)
        if query_parts["code"][0]:
            Oauth2CallbackHandler.code = query_parts["code"][0]
        
        self._set_response()
        self.wfile.write("GET request for {}".format(self.path).encode('utf-8'))


def handle_oauth2_callback(port=21214):
    with HTTPServer(('', port), Oauth2CallbackHandler) as httpd:
        httpd.handle_request()
    #    while not Oauth2CallbackHandler.code:
    # with HTTPServer(('', port), Oauth2CallbackHandler) as httpd:
    #     httpd.serve_forever()
    return Oauth2CallbackHandler.code
    

# Credentials you get from registering a new application
client_id = '02629493e33bb2d1dcf3'

# OAuth endpoints given in the GitHub API documentation
authorization_base_url = 'https://github.com/login/oauth/authorize'
token_url = 'https://github.com/login/oauth/access_token'

# We need to be able to create a new repo on behalf of the user and change its GitHub-Pages settings.
# Thus we need scope="repo" (including private repos), or scope="public_repo" (public repos only, no access to private repos).
# For different scopes, see: https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/scopes-for-oauth-apps
# The required scope will be shown to the user on the authorization_url web page asking the users confirmation.
oa2 = OAuth2Session(client_id, scope="public_repo")

# Redirect user to GitHub for authorization
authorization_url, state = oa2.authorization_url(authorization_base_url)
shell_open(authorization_url)
resp_code = handle_oauth2_callback()
token = oa2.fetch_token(token_url, client_secret=ginder_client_secret, code=resp_code)

# Output and save the token
print(token)
token_str = token['access_token']
path_to_secrets = os.path.join(local_dir_path, 'ginder_secrets.py')
f = open(path_to_secrets, "a")
f.write(f"\nginder_token = '{token_str}'\n")
f.close()

# Test: Fetch a protected resource, i.e. user profile
user = oa2.get('https://api.github.com/user')

bytes = user.content.decode().replace("'", '"')
json_content = json.loads(bytes)
print(json.dumps(json_content, indent=2))

