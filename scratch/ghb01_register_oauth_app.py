import os
import sys
import logging
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
import urllib.parse
from requests_oauthlib import OAuth2Session
from ginder_secrets import ginder_client_secret

# import pygit2
# from github import Github
# from github import Auth

def shell_open(url):
    if sys.platform == "win32":
        os.startfile(url)
    else:
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.call([opener, url])

# From https://gist.github.com/mdonkers/63e115cc0c79b4f6b8b3a6b797e485c7
# class LoggingRequestHandler(BaseHTTPRequestHandler):

#     def __init__(self, *args):
#         self.map_get = {}
#         self.map_post = {}
#         BaseHTTPRequestHandler.__init__(self, *args)    

#     def _set_response(self):
#         self.send_response(200)
#         self.send_header('Content-type', 'text/html')
#         self.end_headers()

#     def do_GET(self):
#         logging.info("GET request,\nPath: %s\nHeaders:\n%s\n", str(self.path), str(self.headers))
#         self._set_response()
#         self.wfile.write("GET request for {}".format(self.path).encode('utf-8'))

#     def do_POST(self):
#         content_length = int(self.headers['Content-Length']) # <--- Gets the size of data
#         post_data = self.rfile.read(content_length) # <--- Gets the data itself
#         logging.info("POST request,\nPath: %s\nHeaders:\n%s\n\nBody:\n%s\n",
#                 str(self.path), str(self.headers), post_data.decode('utf-8'))

#         self._set_response()
#         self.wfile.write("POST request for {}".format(self.path).encode('utf-8'))

# def run(server_class=HTTPServer, handler_class=LoggingRequestHandler, port=8080):
#     logging.basicConfig(level=logging.INFO)
#     server_address = ('', port)
#     httpd = server_class(server_address, handler_class)
#     logging.info('Starting httpd...\n')
#     try:
#         httpd.serve_forever()
#     except KeyboardInterrupt:
#         pass
#     httpd.server_close()
#     logging.info('Stopping httpd...\n')


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

# For different scopes, see: https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/scopes-for-oauth-apps
# We need to be able to create a new repo on behalf of the user, so we need "repo" (including private repos), or 
# "public_repo".
oa2 = OAuth2Session(client_id, scope="public_repo")

# Redirect user to GitHub for authorization
authorization_url, state = oa2.authorization_url(authorization_base_url)
shell_open(authorization_url)
resp_code = handle_oauth2_callback()
token = oa2.fetch_token(token_url, client_secret=ginder_client_secret, code=resp_code)

# Output and save the token
print(token)
token_str = token['access_token']
path_to_secrets = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ginder_secrets.py')
f = open(path_to_secrets, "a")
f.write(f"\nginder_token = '{token_str}'\n")
f.close()

# Test: Fetch a protected resource, i.e. user profile
r = oa2.get('https://api.github.com/user')

bytes = r.content.decode().replace("'", '"')
json_content = json.loads(bytes)
print(json.dumps(json_content, indent=2))

