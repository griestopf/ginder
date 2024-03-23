# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTIBILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

import json
from urllib.parse import urlparse
from urllib.request import urlretrieve
import bpy
import os
import sys
import queue
import ensurepip
import subprocess
import threading
import functools
import requests
import atexit
import time
import platform
import urllib
from http.server import BaseHTTPRequestHandler, HTTPServer
from enum import Enum


# ExportHelper is a helper class, defines filename and
# invoke() function which calls the file selector.
from bpy_extras.io_utils import ExportHelper
from bpy.props import StringProperty, BoolProperty, EnumProperty, IntProperty
from bpy.types import Operator, AddonPreferences

bl_info = {
    "name": "Ginder - GitHub for Blender",
    "author": "Christoph Müller",
    "version": (0, 6),
    "blender": (4, 0, 0),
    "location": "File",
    "description": "Basic git and GitHub operations for .blend files.",
    "warning": "",
    "doc_url": "https://github.com/griestopf/ginder",
    "category": "Scene",
}

the_unique_name_of_the_addon   = "ginder"
the_readable_name_of_the_addon = "Ginder - GitHub for Blender"

the_unique_name_of_the_register_with_github_button = "ginder.register_with_github"
the_unique_name_of_the_deregister_from_github_button = "ginder.deregister_with_github"
the_unique_name_of_the_install_prerequisites_button = "ginder.install_prerequisites"
the_unique_name_of_the_uninstall_prerequisites_button = "ginder.uninstall_prerequisites"
the_unique_name_of_the_restart_blender_button = "ginder.restart_blender"
the_unique_name_of_the_ginder_preferences_button = "ginder.preferences"
the_unique_name_of_the_copy_registration_link_button = "ginder.copy_registration_link"

#######################################################################################################
#
#  UTILITY FUNCTIONS
#
#######################################################################################################

def connected_to_internet(url='https://www.example.com/', timeout=10):
    try:
        _ = requests.head(url, timeout=timeout)
        return True
    except requests.ConnectionError:
        pass
    return False


#get the folder path for the .py file containing this function
def get_path():
    return os.path.dirname(os.path.realpath(__file__))


def report_error(header: str, msg: str):
    ShowMessageBox(msg, header, 'ERROR')
    print(header + ": " + msg)


def ShowMessageBox(message = "", title = "Message Box", icon = 'INFO'):

    def draw(self, context):
        self.layout.label(text=message)

    bpy.context.window_manager.popup_menu(draw, title = title, icon = icon)

#######################################################################################################
#
#  ADD-ON STATE AND PREREQUISITES MANAGEMENT
#
#######################################################################################################

ginder_prerequisites = {}

def check_prerequisites():
    global ginder_prerequisites
    ginder_prerequisites = {'pygit2':False, 'github':False, 'requests_oauthlib':False}
    try:
        import pygit2
        ginder_prerequisites['pygit2'] = True
    except:
        ginder_prerequisites['pygit2'] = False
    try:
        import github
        ginder_prerequisites['github'] = True
    except:
        ginder_prerequisites['github'] = False
    try:
        import requests_oauthlib
        ginder_prerequisites['requests_oauthlib'] = True
    except:
        ginder_prerequisites['requests_oauthlib'] = False
  


def token_present() -> bool:
    token = ''
    try:
        token = GinderPreferences.get_github_token()
    except:
        pass
    return token
    
def check_token(token: str):
    # Try to connnect to GitHub using the token passed to us
    try:
        import github
        auth=github.Auth.Token(token=token)
        g = github.Github(auth=auth)
        user = g.get_user()
        user_name = user.name
    except:
        GinderState.state = GinderState.PREREQ_INSTALLED
        return
    
    g.close()

    # We're still here: notify the main thread
    run_in_main_thread(functools.partial(GinderPreferences.set_github_user,  user_name))
    GinderState.state = GinderState.GITHUB_REGISTERED

    # Try to load the user avatar (if not already loaded during this session)
    if not 'the_avatar_icon' in preview_collections['main']:
        avatar_download_url = urlparse(user.avatar_url)
        _, avatar_ext = os.path.splitext(avatar_download_url.path)
        avatar_local_dir = os.path.join(os.path.dirname(__file__), "icons", f"avatar{avatar_ext}")

        try:
            urlretrieve(user.avatar_url, avatar_local_dir)
            run_in_main_thread(lambda:preview_collections['main'].load('the_avatar_icon', avatar_local_dir, 'IMAGE'))
        except Exception:
            run_in_main_thread(lambda:report_error('ERROR', f'Could not load GitHub avatar from: {user.avatar_url}'))
            pass

#######################################################################################################

class GinderState:
    UNDEFINED = -1
    ADDON_INSTALLED = 0
    INSTALLING_PREREQ = 1
    UNINSTALLING_PREREQ = 2
    READY_FOR_RESTART = 3
    PREREQ_INSTALLED = 4
    REGISTERING_GITHUB = 5
    VALIDATING_TOKEN = 6
    GITHUB_REGISTERED = 7
    LAST_STATE = 8

    state = UNDEFINED

    state_descriptions = [
        "Necessary python modules not installed", 
        "Installing necessary python modules", 
        "Uninstalling python modules", 
        "Blender needs to be restarted", 
        "Ready to register with GitHub",
        "Finish the Ginder ↔ GitHub registration in your Web browser!",
        "Checking GitHub access",
        "Ready"
        ]

    def state_description() -> str:
        if 0 <= GinderState.state and GinderState.state < GinderState.LAST_STATE:
            return GinderState.state_descriptions[GinderState.state]
        return 'Undefined'

    @staticmethod
    def init():
        # We are here, so we are installed!
        GinderState.state = GinderState.ADDON_INSTALLED

        check_prerequisites()
        if not (ginder_prerequisites['pygit2'] and ginder_prerequisites['github'] and ginder_prerequisites['requests_oauthlib']):
            return

        # All necessary python modules seem to be installed
        GinderState.state = GinderState.PREREQ_INSTALLED

        token = token_present()
        if  not token:
            return

        # There is a token. Check if we can use it to access GitHub
        GinderState.state = GinderState.VALIDATING_TOKEN
        check_token_thread = threading.Thread(target=functools.partial(check_token, token))
        check_token_thread.start()
        return GinderState.state


#######################################################################################################
#
#  UI UPDATE, PROGRESS BAR AND CALL INTO MAIN THREAD MANAGEMENT
#
#######################################################################################################

# This function can safely be called in another thread.
# The function will be executed when the timer runs the next time.
def run_in_main_thread(function):
    UIUpdate.execution_queue.put(function)


class UIUpdate:
    REDRAW = 0
    PROGRESS_FINITE = 1
    PROGRESS_INFINITE = 2

    progress_mode:int = REDRAW

    progress:float = 0
    duration:float = 0
    endat:float = 0
    startat:float = 0
    spf:float = 1/2 # 2 frames per second, fair enough for status updates
    speed:float = 0
    message:str = ''
    area:bpy.types.Area = None
    stopit:bool = False
    execution_queue:queue.Queue

    @staticmethod
    def start_pulse(area:bpy.types.Area = None, fps:float = 2):
        UIUpdate.area = area
        if not bpy.app.timers.is_registered(UIUpdate.pulse):
            UIUpdate.spf = 1/fps
            UIUpdate.stopit = False
            UIUpdate.execution_queue = queue.Queue()
            bpy.app.timers.register(UIUpdate.pulse)

    @staticmethod
    def stop_pulse():
        UIUpdate.stopit = True
                
    @staticmethod
    def progress_init(area:bpy.types.Area, fps:float = 10, msg:str = ''):
        UIUpdate.progress = 0
        UIUpdate.duration = 0
        UIUpdate.endat = 0
        UIUpdate.startat = 0
        UIUpdate.spf = 1/fps
        UIUpdate.message = msg
        UIUpdate.area = area
        UIUpdate.progress_mode = UIUpdate.PROGRESS_FINITE
        UIUpdate.start_pulse(area)
    
    @staticmethod
    def progress_init_indefinite(area:bpy.types.Area, duration:float = 1, fps:float = 10, msg:str = ''):
        UIUpdate.progress = 0
        UIUpdate.duration = 0
        UIUpdate.endat = 1
        UIUpdate.startat = 0
        UIUpdate.spf = 1/fps
        UIUpdate.message = msg
        UIUpdate.speed = (UIUpdate.endat - UIUpdate.startat) / duration
        UIUpdate.area = area
        UIUpdate.progress_mode = UIUpdate.PROGRESS_INFINITE
        UIUpdate.start_pulse(area)

    @staticmethod
    def end_progress():
        UIUpdate.spf = 1/2 # 2 beats per second, fair enough for status updates
        UIUpdate.progress_mode = UIUpdate.REDRAW

    @staticmethod
    def milestone(endat:float, msg:str=None, duration:float = 3):
        if msg:
            UIUpdate.message = msg
        UIUpdate.startat = UIUpdate.progress
        UIUpdate.duration = duration
        UIUpdate.endat = endat
        UIUpdate.speed = (endat - UIUpdate.startat) / duration

    @staticmethod
    def pulse():
        while not UIUpdate.execution_queue.empty():
            function = UIUpdate.execution_queue.get()
            # print(f'calling {function.__name__ if hasattr(function, "__name__") else "nameless function"}')
            function()

        if UIUpdate.stopit: # or (UIUpdate.area and UIUpdate.area.type == 'EMPTY'):
            return None

        match UIUpdate.progress_mode:
            case UIUpdate.PROGRESS_FINITE:
                UIUpdate.progress += UIUpdate.speed * UIUpdate.spf
                if UIUpdate.progress >= UIUpdate.startat + 0.5*(UIUpdate.endat - UIUpdate.startat):
                    UIUpdate.speed *= 0.5
                    UIUpdate.startat = UIUpdate.progress
            case UIUpdate.PROGRESS_INFINITE:
                UIUpdate.progress += UIUpdate.speed * UIUpdate.spf
                if UIUpdate.progress >= UIUpdate.endat or UIUpdate.progress < UIUpdate.startat:
                    UIUpdate.speed = -UIUpdate.speed
        
        # print(f'pulsing every {UIUpdate.spf} second.')

        if UIUpdate.area and not UIUpdate.area.type == 'EMPTY':
            # TODO: Make sure the area is still valid
            UIUpdate.area.tag_redraw()
        return UIUpdate.spf


#######################################################################################################
#
#  INSTALL PREREQUISITES
#
#######################################################################################################

def install_prerequisites() -> bool:
    check_prerequisites()
    try:
        n = len(ginder_prerequisites) - sum(ginder_prerequisites.values())
        n += 1  # For Pip
        i=1.0
        # deprecated as of 2.91: pybin = bpy.app.binary_path_python. Instead use 
        pybin = sys.executable

        UIUpdate.milestone(i/n, 'Installing/Updating pip', 2)
        ensurepip.bootstrap()
        subprocess.check_call([pybin, '-m', 'pip', 'install', '--upgrade', 'pip'])

        if not ginder_prerequisites['pygit2']:
            i += 1
            UIUpdate.milestone(i/n, 'Installing pygit2', 2)
            subprocess.check_call([pybin, '-m', 'pip', 'install', 'pygit2'])
        if not ginder_prerequisites['github']:
            i += 1
            UIUpdate.milestone(i/n, 'Installing PyGithub', 2)
            subprocess.check_call([pybin, '-m', 'pip', 'install', 'PyGithub'])
        if not ginder_prerequisites['requests_oauthlib']:
            i += 1
            UIUpdate.milestone(i/n, 'Installing requests-oauthlib', 2)
            subprocess.check_call([pybin, '-m', 'pip', 'install', 'requests-oauthlib'])
    except Exception as ex:
        run_in_main_thread(functools.partial(report_error, 'ERROR Installing Ginder Prerequisites', f'Could not pip install one or more modules required by Ginder\n{str(ex)}'))
        UIUpdate.end_progress()
        return False
    check_prerequisites()
    if ginder_prerequisites['pygit2'] and ginder_prerequisites['github'] and ginder_prerequisites['requests_oauthlib']:
        GinderState.state = GinderState.PREREQ_INSTALLED
    else:
        GinderState.state = GinderState.READY_FOR_RESTART
    UIUpdate.end_progress()
    return True

class InstallPrerequisitesOperator(bpy.types.Operator):
    """Download and install python modules required by this Add-on"""
    bl_idname = the_unique_name_of_the_install_prerequisites_button
    bl_label = "Install Prerequisites"

    def execute(self, context):
        if GinderState.state != GinderState.ADDON_INSTALLED:
            report_error('Ginder installation', 'The AddOn is in an unexpected state')
            return {'CANCELLED'}

        UIUpdate.progress_init(context.area)
        install_prereq_thread = threading.Thread(target=install_prerequisites)
        install_prereq_thread.start()
        GinderState.state = GinderState.INSTALLING_PREREQ
        return {'FINISHED'}


#######################################################################################################
#
#  UNINSTALL PREREQUISITES
#
#######################################################################################################

def uninstall_prerequisites() -> bool:
    try:
        n = 3.0
        i=1.0
        # deprecated as of 2.91: pybin = bpy.app.binary_path_python. Instead use 
        pybin = sys.executable

        UIUpdate.milestone(i/n, 'Uninstalling requests-oauthlib', 2)
        subprocess.check_call([pybin, '-m', 'pip', 'uninstall', '-y', 'requests-oauthlib'])

        i += 1
        UIUpdate.milestone(i/n, 'Uninstalling PyGithub', 2)
        subprocess.check_call([pybin, '-m', 'pip', 'uninstall', '-y', 'PyGithub'])

        i += 1
        UIUpdate.milestone(i/n, 'Uninstalling pygit2', 2)
        subprocess.check_call([pybin, '-m', 'pip', 'uninstall', '-y', 'pygit2'])
    except Exception as ex:
        run_in_main_thread(functools.partial(report_error, 'ERROR Uninstalling Ginder Prerequisites', f'Could not pip uninstall one modules\n{str(ex)}'))
        UIUpdate.end_progress()
        return False
    check_prerequisites()
    if not (ginder_prerequisites['pygit2'] and ginder_prerequisites['github'] and ginder_prerequisites['requests_oauthlib']):
        GinderState.state = GinderState.PREREQ_INSTALLED
    else:
        GinderState.state = GinderState.READY_FOR_RESTART
    UIUpdate.end_progress()
    return True


class UninstallPrerequisitesOperator(bpy.types.Operator):
    """Remove python modules installed by this Add-on. Click only if you plan to uninstall this Add-on."""
    bl_idname = the_unique_name_of_the_uninstall_prerequisites_button
    bl_label = "Uninstall Prerequisites"

    def execute(self, context):
        if GinderState.state != GinderState.PREREQ_INSTALLED:
            report_error('Ginder installation', 'The AddOn is in an unexpected state')
            return {'CANCELLED'}

        UIUpdate.progress_init(context.area)
        install_prereq_thread = threading.Thread(target=uninstall_prerequisites)
        install_prereq_thread.start()
        GinderState.state = GinderState.UNINSTALLING_PREREQ
        return {'FINISHED'}

#######################################################################################################
#
#  RESTART BLENDER
#
#######################################################################################################

def launch():
    """
    launch the blender process
    """
    blender_exe = bpy.app.binary_path
    if platform.system() == "Windows": 
        head, tail = os.path.split(blender_exe)
        blender_launcher = os.path.join(head,"blender-launcher.exe")
        # subprocess.run([blender_launcher, "--python-expr", "import bpy; bpy.ops.wm.recover_last_session()"])
        subprocess.Popen(
            args = f'{blender_launcher} --python-expr "import bpy; bpy.ops.wm.recover_last_session()"',
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS)
    else: 
        subprocess.Popen(
            args = f'{blender_exe} --python-expr "import bpy; bpy.ops.wm.recover_last_session()"',
            start_new_session=True)
        # subprocess.run([blender_exe, '--python-expr', '"import bpy; bpy.ops.wm.recover_last_session()"'])

class RestartBlenderOperator(bpy.types.Operator):
    """Restart Blender to reflect changes by previous installation/uninstallation of python modules"""
    bl_idname = the_unique_name_of_the_restart_blender_button
    bl_label = "Restart Blender"

    def execute(self, context):

        if bpy.data.is_dirty:
            report_error('Warning - Unsaved Work', 'Unsaved changes - Blender will not restart. Save your work and re-start Blender.')
            return {'CANCELLED'}

        atexit.register(launch)
        time.sleep(1)
        bpy.ops.wm.quit_blender('INVOKE_DEFAULT')
        return {'FINISHED'}

#######################################################################################################
#
#  REGISTER WITH GitHub
#
#######################################################################################################

ginder_oauth2_client_id = '02629493e33bb2d1dcf3'
ginder_client_secret = 'd9fbc6d5a0dcb4d4215b91c4fa669d9ee86a1643'
github_authorization_base_url = 'https://github.com/login/oauth/authorize'
github_token_url = 'https://github.com/login/oauth/access_token'

# HTTP-Callback Handler inspired by
# https://gist.github.com/mdonkers/63e115cc0c79b4f6b8b3a6b797e485c7

class Oauth2CallbackHandler(BaseHTTPRequestHandler):
    code = ''
    
    def _set_response(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()

    def do_GET(self):
        url_parts = urllib.parse.urlparse(self.path)
        query_parts = urllib.parse.parse_qs(url_parts.query)
        if query_parts["code"][0]:
            Oauth2CallbackHandler.code = query_parts["code"][0]
        
        self._set_response()
        # self.wfile.write("GET request for {}".format(self.path).encode('utf-8'))
        self.wfile.write('''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8" />
    <title>title</title>
</head>
<body style="font-family: 'Tahoma',sans-serif; margin-left: 5%; margin-right:5%" >
    <h1>Ginder authorized ✅</h1>
    <p>Congratulations, you successfully registered your installation of <b>Ginder</b>, the GitHub Add-on for Blender.</p>
    <p>You can close this tab and proceed back to Blender.</p>
</body>
</html>'''
                         .encode('utf-8'))

def handle_oauth2_callback(port=21214):
    # print('handling oauth2 request')
    with HTTPServer(('', port), Oauth2CallbackHandler) as httpd:
        httpd.handle_request()
    return Oauth2CallbackHandler.code

def do_register_with_github():
    try:
        # print('now in do_register_with_github')
        from requests_oauthlib import OAuth2Session
        # We need to be able to create a new repo on behalf of the user and change its GitHub-Pages settings.
        # Thus we need scope="repo" (including private repos), or scope="public_repo" (public repos only, no access to private repos).
        # For different scopes, see: https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/scopes-for-oauth-apps
        # The required scope will be shown to the user on the authorization_url web page asking the users confirmation.
        oa2 = OAuth2Session(ginder_oauth2_client_id, scope="public_repo")

        # Redirect user to GitHub for authorization
        authorization_url, state = oa2.authorization_url(github_authorization_base_url)
        # Do not put a breakpoint in between the following two calls. Otherwise the OAuth authorization site could send the response before the handler is set-up
        # print('Right before opening registration url and starting request handler')
        run_in_main_thread(functools.partial(do_url_open, authorization_url))
        resp_code = handle_oauth2_callback()

        # print('request handled, fetching token')
        token_dict = oa2.fetch_token(github_token_url, client_secret=ginder_client_secret, code=resp_code)
        token = token_dict['access_token']
        run_in_main_thread(functools.partial(GinderPreferences.set_github_token, token))

        # print('Checking token')
        check_token(token)

        UIUpdate.end_progress()
        GinderState.state = GinderState.GITHUB_REGISTERED
        # print(f"GinderState.state: {GinderState.state}")
    except Exception as ex:
        run_in_main_thread(functools.partial(report_error, 'ERROR', f'Exception in do_register_with_github: {str(ex)}'))
        raise


current_url = ''

def do_url_open(url:str):
    global current_url
    current_url = url
    bpy.ops.wm.url_open(url=url)
    

class RegisterWithGitHubOperator(bpy.types.Operator):
    """Opens up your Web browser showing a page where you can register Ginder (this Add-on) with your user account. This will allow Ginder to access your public GitHub repositories"""
    bl_idname = the_unique_name_of_the_register_with_github_button
    bl_label = "Register with GitHub"

    def execute(self, context):
        # print('executing RegisterWithGitHubOperator')
        if GinderState.state != GinderState.PREREQ_INSTALLED:
            report_error('Ginder Installation', 'The Add-On is in an unexpected state')
            return {'CANCELLED'}

        # print('Starting prog anim, do_register')
        UIUpdate.progress_init_indefinite(context.area)
        register_with_github_thread = threading.Thread(target=do_register_with_github)
        register_with_github_thread.start()
        GinderState.state = GinderState.REGISTERING_GITHUB
        # print('returning from execute')
        return {'FINISHED'}

#######################################################################################################
#
#  DEREGISTER FROM GitHub
#
#######################################################################################################

# ENDPOINT SEEMS TO BE DEFUNCT OR MISUNDERSTOOD 
#def do_deregister_from_github():
#     # Do this: https://docs.github.com/en/rest/apps/oauth-applications?apiVersion=2022-11-28#delete-an-app-token
#     #curl -L \
#     # -X DELETE \
#     # -H "Accept: application/vnd.github+json" \
#     # -H "Authorization: Bearer <YOUR-TOKEN>" \
#     # -H "X-GitHub-Api-Version: 2022-11-28" \
#     # https://api.github.com/applications/<APP-ID???>/token \
#     # -d '{"access_token":"<YOUR-TOKEN>???"}'

#     if GinderState.state != GinderState.GITHUB_REGISTERED:
#         return
    
#     token = GinderPreferences.get_github_token()
#     headers = {
#         "Accept"                :  "application/vnd.github+json",
#         "Authorization"         : f"Bearer {token}",
#         "X-GitHub-Api-Version"  :  "2022-11-28"
#     }
#     data = {
#         "access_token"  : token,
#     }
#     url = f'https://api.github.com/applications/{ginder_oauth2_client_id}/token'
#     res = requests.delete(url=url, headers=headers, json=data)
#     if (200 <= res.status_code and res.status_code < 300):
#         GinderState.state = GinderState.PREREQ_INSTALLED
#     else:
#         report_error('ERROR', 'Could not deregister from GitHub.')

class DeregisterFromGitHubOperator(bpy.types.Operator):
    """Reset GitHub registration. To finally remove your Ginder registration from GitHub, revoke Ginder access from github.com/settings/applications"""
    bl_idname = the_unique_name_of_the_deregister_from_github_button
    bl_label = "Reset GitHub registration"

    def execute(self, context):
        if GinderState.state != GinderState.GITHUB_REGISTERED:
            return {'FINISHED'}
        GinderPreferences.set_github_token('')
        GinderPreferences.set_github_user('')
        del preview_collections['main']['the_avatar_icon']
        GinderState.state = GinderState.PREREQ_INSTALLED
        do_url_open('https://github.com/settings/applications')
        return {'FINISHED'}

#######################################################################################################
#
#  OPEN Ginder PREFERENCES DIALOG
#
#######################################################################################################

class OpenGinderPrefsOperator(bpy.types.Operator):
    """Open the Ginder Add-On's preferences"""
    bl_idname = the_unique_name_of_the_ginder_preferences_button
    bl_label = "Ginder Preferences"

    def execute(self, context):
        bpy.ops.screen.userpref_show()
        bpy.context.preferences.active_section = 'ADDONS'
        bpy.data.window_managers["WinMan"].addon_search = the_readable_name_of_the_addon
        bpy.data.window_managers["WinMan"].addon_support = {'COMMUNITY'}
        bpy.ops.preferences.addon_show(module=the_unique_name_of_the_addon)
        return {'FINISHED'}
    
#######################################################################################################
#
#  COPY GitHub REGISTRATION LINK TO CLIPBOARD
#
#######################################################################################################

def copy2clip(txt:str):
    match platform.system():
        case "Windows":
            # escape ampersand with triple caret (https://superuser.com/questions/550048/is-there-an-escape-for-character-in-the-command-prompt)
            escaped_link = txt.strip().replace('&', '^^^&')
            cmd='echo '+escaped_link+'|clip'
        case "Linux":
            # escape ampersand with backslash (https://askubuntu.com/questions/50898/how-to-skip-the-evaluation-of-ampersand-in-command-line)
            escaped_link = txt.strip().replace('&', '\\&')
            cmd='echo '+escaped_link+'|xclip'
        case "Darwin": # (open-sourced base part of macOS)
            # escape ampersand with backslash (https://askubuntu.com/questions/50898/how-to-skip-the-evaluation-of-ampersand-in-command-line)
            escaped_link = txt.strip().replace('&', '\\&')
            cmd='echo '+escaped_link+'|pbcopy'
    return subprocess.check_call(cmd, shell=True)

class CopyRegistrationLinkOperator(bpy.types.Operator):
    """If your browser does not open the Ginder registration page autmatically, click this button to copy the GitHub registration link to the clipboard. Afterwards, open your browser and paste the copied link"""
    bl_idname = the_unique_name_of_the_copy_registration_link_button
    bl_label = "Copy Registration Link to Clipboard"

    def execute(self, context):
        if current_url:
            copy2clip(current_url)
        else:
            report_error('ERROR', 'GitHub registration URL not set.')
        return {'FINISHED'}
    
 

#######################################################################################################
#
#  Ginder PREFERENCES DATA AND DIALOG
#
#######################################################################################################

class GinderPreferences(AddonPreferences):
    # this must match the add-on name, use '__package__'
    # when defining this in a submodule of a python package.
    bl_idname = the_unique_name_of_the_addon

    @staticmethod
    def set_github_token(token:str) -> None:
        bpy.context.preferences.addons[the_unique_name_of_the_addon].preferences.github_token = token

    @staticmethod
    def get_github_token() -> str:
        return bpy.context.preferences.addons[the_unique_name_of_the_addon].preferences.github_token

    github_token: StringProperty(
        name="GitHub Token",
        description="GitHub Access token registered by the user with the Ginder Add-on.",
    ) # type: ignore

    @staticmethod
    def set_github_user(user:str) -> None:
        bpy.context.preferences.addons[the_unique_name_of_the_addon].preferences.github_user = user

    @staticmethod
    def get_github_user() -> str:
        return bpy.context.preferences.addons[the_unique_name_of_the_addon].preferences.github_user

    github_user: StringProperty(
        name="GitHub User",
        description="GitHub user registered with the Ginder Add-on.",
    ) # type: ignore
    number: IntProperty(
        name="Example Number",
        default=4,
    ) # type: ignore
    boolean: BoolProperty(
        name="Example Boolean",
        default=False,
    ) # type: ignore

    def draw(self, context):
        layout = self.layout
        UIUpdate.start_pulse(context.area)

        if GinderState.state == GinderState.UNDEFINED:
            GinderState.init()
            

        status_text = f'Connected to GitHub as {GinderPreferences.get_github_user()}' if GinderState.state == GinderState.GITHUB_REGISTERED else GinderState.state_description() 
        avatar_icon = preview_collections['main']['the_avatar_icon'].icon_id if 'the_avatar_icon' in preview_collections['main'] else preview_collections['main']['the_avatar_unknown_icon'].icon_id

        # GINDER STATUS
        box = layout.box()
        row = box.row()
        row.scale_y = 2
        row.template_icon(icon_value = avatar_icon, scale=1)
        col = row.column()
        col.scale_y = 0.5
        # STATUSBOX LINE ONE
        #col.label(text = status_text)
        # STATUSBOX LINE TWO
        #col.operator(the_unique_name_of_the_restart_blender_button, icon='BLENDER')

        match GinderState.state:
            case GinderState.ADDON_INSTALLED:
                col.label(text = status_text)
                col.operator(the_unique_name_of_the_install_prerequisites_button, icon='SCRIPT')

            case GinderState.INSTALLING_PREREQ |GinderState.UNINSTALLING_PREREQ:
                col.label(text = status_text)
                col.progress(factor=UIUpdate.progress, type = 'BAR', text=UIUpdate.message)

            case GinderState.READY_FOR_RESTART:
                col.label(text = status_text)
                col.operator(the_unique_name_of_the_restart_blender_button, icon='BLENDER')
                
            case GinderState.PREREQ_INSTALLED:
                col.label(text = status_text)
                col.operator(the_unique_name_of_the_register_with_github_button, icon_value = preview_collections['main']['the_github_icon'].icon_id)
                col.operator(the_unique_name_of_the_uninstall_prerequisites_button, icon='CANCEL')

            case GinderState.REGISTERING_GITHUB:
                col.progress(factor=UIUpdate.progress, type = 'RING', text=status_text)
                col.operator(the_unique_name_of_the_copy_registration_link_button, icon='URL')

            case GinderState.GITHUB_REGISTERED:
                col.label(text = status_text)
                col.operator(the_unique_name_of_the_deregister_from_github_button, icon='CANCEL')

            case _:
                col.label(text = 'Undefined State. Try to disable/enable or to remove/re-install Ginder')

        row.template_icon(icon_value = preview_collections['main']['the_ginder_icon_l'].icon_id, scale=1)



#######################################################################################################
#
#  File -> Ginder MENU
#
#######################################################################################################

class GinderMenu(bpy.types.Menu):
    bl_label = 'Ginder Menu'
    bl_idname = 'FILE_MT_ginder_menu'

    def draw(self, context):
        UIUpdate.start_pulse(context.area)

        if GinderState.state == GinderState.UNDEFINED:
            GinderState.init()

        layout = self.layout
        layout.operator('wm.open_mainfile')
        layout.operator('wm.save_as_mainfile').copy = True
        layout.operator(the_unique_name_of_the_ginder_preferences_button)


#######################################################################################################

def draw_ginder_menu(self, context):
    layout = self.layout
    layout.menu(GinderMenu.bl_idname, text = 'Ginder - darepo', icon_value = preview_collections['main']["the_ginder_icon"].icon_id)


#######################################################################################################
#
#  Add-On REGISTRATION and DEREGISTRATION
#
#######################################################################################################


# We can store multiple preview collections here,
# however in this example we only store 'main'
preview_collections = {}

# Register and add to the "file selector" menu (required to use F3 search "Text Export Operator" for quick access).
def register():
    # Custom icon registration taken from https://docs.blender.org/api/4.0/bpy.utils.previews.html
    # Note that preview collections returned by bpy.utils.previews
    # are regular py objects - you can use them to store custom data.
    import bpy.utils.previews
    pcoll = bpy.utils.previews.new()

    # path to the folder where the icon is
    # the path is calculated relative to this py file inside the addon folder
    my_icons_dir = os.path.join(os.path.dirname(__file__), 'icons')

    # load a preview thumbnail of a file and store in the previews collection
    pcoll.load('the_github_icon', os.path.join(my_icons_dir, 'github_icon.png'), 'IMAGE')
    pcoll.load('the_ginder_icon', os.path.join(my_icons_dir, 'ginder_icon_w.png'), 'IMAGE')
    pcoll.load('the_ginder_icon_l', os.path.join(my_icons_dir, 'ginder_icon_g64.png'), 'IMAGE')
    pcoll.load('the_avatar_unknown_icon', os.path.join(my_icons_dir, 'avatar_unknown.png'), 'IMAGE')

    preview_collections['main'] = pcoll

    bpy.utils.register_class(RegisterWithGitHubOperator)
    bpy.utils.register_class(DeregisterFromGitHubOperator)
    bpy.utils.register_class(InstallPrerequisitesOperator)
    bpy.utils.register_class(UninstallPrerequisitesOperator)
    bpy.utils.register_class(RestartBlenderOperator)
    bpy.utils.register_class(CopyRegistrationLinkOperator)
    bpy.utils.register_class(GinderPreferences)
    bpy.utils.register_class(OpenGinderPrefsOperator)
    bpy.utils.register_class(GinderMenu)
    bpy.types.TOPBAR_MT_file.prepend(draw_ginder_menu)
    bpy.context.preferences.use_preferences_save = True # see https://blender.stackexchange.com/questions/157677/add-on-preferences-auto-saving-bug
    
    # Check once on startup
    UIUpdate.start_pulse()
    GinderState.init()

def unregister():
    UIUpdate.stop_pulse()
    bpy.types.TOPBAR_MT_file.remove(draw_ginder_menu)
    bpy.utils.unregister_class(GinderMenu)
    bpy.utils.unregister_class(OpenGinderPrefsOperator)
    bpy.utils.unregister_class(GinderPreferences)
    bpy.utils.unregister_class(RestartBlenderOperator)
    bpy.utils.unregister_class(CopyRegistrationLinkOperator)
    bpy.utils.unregister_class(UninstallPrerequisitesOperator)
    bpy.utils.unregister_class(InstallPrerequisitesOperator)
    bpy.utils.unregister_class(DeregisterFromGitHubOperator)
    bpy.utils.unregister_class(RegisterWithGitHubOperator)

    # Custom icon deregistration
    for pcoll in preview_collections.values():
         bpy.utils.previews.remove(pcoll)
    preview_collections.clear()

if __name__ == "__main__":
    register()
