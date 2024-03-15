# Things to install in blender
# Pip-Name -> import name
# pip install pygit2               ->  import pygit2
# pip install PyGithub             ->  from github import Github
#                                      from github import Auth
# pip install requests-oauthlib    ->  from requests_oauthlib import OAuth2Session
import ensurepip
import subprocess
import sys

ensurepip.bootstrap()
# deprecated as of 2.91: pybin = bpy.app.binary_path_python. Instead use 
pybin = sys.executable
subprocess.check_call([pybin, '-m', 'pip', 'uninstall', '-y', 'pygit2'])
subprocess.check_call([pybin, '-m', 'pip', 'uninstall', '-y', 'PyGithub'])
subprocess.check_call([pybin, '-m', 'pip', 'uninstall', '-y', 'requests-oauthlib'])
