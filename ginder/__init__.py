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
from bpy.app.handlers import persistent
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
import string
import random
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

id_for_addon   = "ginder"
the_readable_name_of_the_addon = "Ginder - GitHub for Blender"

id_for_register_with_github_operator = "ginder.register_with_github"
id_for_deregister_from_github_operator = "ginder.deregister_with_github"
id_for_install_prerequisites_operator = "ginder.install_prerequisites"
id_for_uninstall_prerequisites_operator = "ginder.uninstall_prerequisites"
id_for_restart_blender_operator = "ginder.restart_blender"
id_for_ginder_preferences_operator = "ginder.preferences"
id_for_copy_registration_link_operator = "ginder.copy_registration_link"
id_for_ginder_open_users_github_page_operator = "ginder.open_users_github_page"
id_for_create_new_presentation_repo_operator = "ginder.create_new_presentation_repo"
id_for_ginder_open_repos_github_page_operator = "ginder.open_repos_github_page"
id_for_commit_to_repo_operator = "ginder.commit_to_repo"
id_for_push_to_remote_operator = "ginder.push_to_remote"
id_for_pull_from_remote_operator = "ginder.pull_from_remote"
id_for_merge_theirs_operator = "ginder.merge_theirs"
id_for_merge_ours_operator = "ginder.merge_ours"

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
        
    try:
        useremail = next(item for item in user.get_emails() if item.primary == True).email
    except:
        useremail = "Noreply"
    g.close()

    # We're still here: notify the main thread
    run_in_main_thread(functools.partial(GinderGit.set_user,  user, useremail))
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

    @staticmethod
    def get_user_name():
        if not GinderState.state == GinderState.GITHUB_REGISTERED:
            raise Exception(f'Cannot access GitHub user settings due to unexpected GinderState. Expected GITHUB_REGISTERED, is {str(GinderState.state)}.')

        ret = ''
        if GinderGit.github_user:
            login = GinderGit.github_user.login
            user_name = GinderGit.github_user.name
            if user_name and login:
                ret = f'{user_name} ({login})'
            elif login:
                ret = login
        return ret

    @staticmethod
    def get_login_name():
        if not GinderState.state == GinderState.GITHUB_REGISTERED:
            raise Exception(f'Cannot access GitHub user settings due to unexpected GinderState. Expected GITHUB_REGISTERED, is {str(GinderState.state)}.')

        ret = ''
        if GinderGit.github_user:
            ret = GinderGit.github_user.login
        return ret

    @staticmethod
    def pygit2_present():
        return GinderState.state == GinderState.GITHUB_REGISTERED or GinderState.state == GinderState.PREREQ_INSTALLED

    @staticmethod
    @persistent
    def post_load_handler(blendfile):
        GinderGit.check_and_open_repo(blendfile)

    @staticmethod
    def install_post_load_handler():
        # Perform 
        #  ´´´bpy.app.handlers.load_post.append(GinderState.post_load_handler)´´´
        # once and only once
        fn_list = bpy.app.handlers.load_post
        fn = GinderState.post_load_handler
        fn_name = fn.__name__
        fn_module = fn.__module__
        for i in range(len(fn_list) - 1, -1, -1):
            if fn_list[i].__name__ == fn_name and fn_list[i].__module__ == fn_module:
                del fn_list[i]
        fn_list.append(fn)


#######################################################################################################
#
#  Git & GitHub actions
#
#######################################################################################################

class GinderGit:
    github_user = None
    github_useremail: str = None # Must be set by user
    repo_dir:str = None
    github_repo = None # This is the remote presentation repo (origin) as a PyGithub-typedobject
    remote_repo = None # This is the remote presentation repo (origin) as a pygit2-typed object (https://www.pygit2.org/remotes.html#pygit2.Remote)
    local_repo = None  # This is the local presentation repo (clone of origin) as a pygit2-typed object
    local_reponame: str = None    # probably the same as remote_reponame (if any)
    remote_username: str = None   # Probably the same as github_user.login but not necessarily
    remote_reponame: str = None 
    githubpages_url: str = None
    last_fetch_time:float = 0.0
    fetch_period:float = 15.0

    @staticmethod
    def set_user(user, useremail):
        GinderGit.github_user = user
        GinderGit.github_useremail = useremail

    @staticmethod
    def check_and_open_repo(filepath):
        # Reset all repo-related settings
        GinderGit.repo_dir = None
        GinderGit.github_repo = None
        GinderGit.remote_repo = None
        GinderGit.local_repo = None
        GinderGit.local_reponame = None
        GinderGit.remote_username = None
        GinderGit.remote_reponame = None 
        GinderGit.githubpages_url = None
                
        # Check if we can safely perform
        if not GinderState.pygit2_present():
            raise Exception('check_for_repo() called without prerequisites installed.')
        if not filepath:
            raise Exception('check_for_repo() called without filepath specified.')
        import pygit2

        # Try to find a local git repo along the path
        curdir = os.path.dirname(filepath)
        GinderGit.repo_dir = pygit2.discover_repository(curdir) # yields something like "C:/Develop/REPONAME/.git/"
        if not GinderGit.repo_dir:
            return False
        GinderGit.repo_dir.replace('\\', '/')
        GinderGit.local_repo = pygit2.Repository(GinderGit.repo_dir)
        pieces = GinderGit.repo_dir.split('/')
        GinderGit.local_reponame = pieces[-3]

        # Check if there is a remote (the 'origin')
        GinderGit.remote_repo = GinderGit.local_repo.remotes[0]
        urlstr = GinderGit.remote_repo.url
        url = urllib.parse.urlparse(urlstr)
        pieces = url.path.split('/')
        GinderGit.remote_username = pieces[-2]
        reponame = pieces[-1]
        GinderGit.remote_reponame = reponame.split('.')[0]

        # Try to connect to the remote on GitHub
        from github import Github
        from github import Auth
        auth=Auth.Token(GinderPreferences.get_github_token())
        g = Github(auth=auth)
        GinderGit.github_repo = g.get_repo(f'{GinderGit.remote_username}/{GinderGit.remote_reponame}')
        GinderGit.get_github_page_url()
        g.close()

        # Fetch any pending changes
        GinderGit.refetch()
        return True

    @staticmethod
    def sync_repo():
        if not GinderState.pygit2_present():
            raise Exception('sync_repo() called without prerequisites installed.')
        if not GinderGit.repo_present():
            raise Exception('sync_repo() called without current github repo')

    @staticmethod
    def create_new_repo(repo_name:str, template_username:str, template_reponame:str):
        if not GinderGit.github_user:
            raise Exception('create_new_repo() called without registered user')
        from github import Github
        from github import Auth
        auth=Auth.Token(GinderPreferences.get_github_token())
        g = Github(auth=auth)

        template = f'{template_username}/{template_reponame}'
        template_repo = g.get_repo(template)

        GinderGit.github_repo = GinderGit.github_user.create_repo_from_template(repo_name, template_repo, description='For debugging purposes only', include_all_branches=False, private=False)
        # We created the new remote repo on behalf of the user with the given name, so we know the user name and the repo
        GinderGit.remote_username = GinderGit.github_user.login
        GinderGit.remote_reponame = repo_name

        g.close()

    @staticmethod
    def get_github_page_url():
        # PyGithub seems to lack this API, so we need to CURL it by hand:
        # curl -L -X GET -H "Accept: application/vnd.github+json" -H "Authorization: Bearer <TOKEN>" -H "X-GitHub-Api-Version: 2022-11-28" https://api.github.com/repos/<user_login>/<repo_name>/pages
        #
        # yields:
        # 
        # {
        #  ...
        #  "html_url": "https://<user_login>.github.io/<repo_name>/",
        #  ...
        # }
        if not GinderGit.remote_username:
            raise Exception('get_github_page_url() called without remote user name')
        if not GinderGit.github_repo:
            raise Exception('get_github_page_url() called without remote repo name')

        headers = {
            "Accept"                :  "application/vnd.github+json",
            "Authorization"         : f"Bearer {GinderPreferences.get_github_token()}",
            "X-GitHub-Api-Version"  :  "2022-11-28"
        }
      
        url = f'https://api.github.com/repos/{GinderGit.remote_username}/{GinderGit.remote_reponame}/pages'
        
        res = requests.get(url=url, headers=headers)
        if 200 <= res.status_code and res.status_code <= 300:
            GinderGit.githubpages_url = res.json()['html_url']
        else:
            raise Exception(f'Could not retrieve GitHub-page url for repo \'{GinderGit.remote_reponame}\' owned by \'{GinderGit.remote_username}\'')
        
    @staticmethod
    def enable_github_pages():
        if not GinderGit.github_user:
            raise Exception('enable_github_pages() called without registered user')
        if not GinderGit.github_repo:
            raise Exception('enable_github_pages() called without current github repo')

        headers = {
            "Accept"                :  "application/vnd.github+json",
            "Authorization"         : f"Bearer {GinderPreferences.get_github_token()}",
            "X-GitHub-Api-Version"  :  "2022-11-28"
        }
        data = {
            "build_type"  : "workflow",
            "source"      : {
                "branch" :"main",
                "path":"/docs"
            }    
        }
        url = f'https://api.github.com/repos/{GinderGit.github_user.login}/{GinderGit.github_repo.name}/pages'
        
        # PyGithub seems to lack this API, so we need to CURL it by hand
        #curl -L -X POST -H "Accept: application/vnd.github+json" -H "Authorization: Bearer <TOKEN>" -H "X-GitHub-Api-Version: 2022-11-28" https://api.github.com/repos/griestopf/FromFreeDeeTest/pages -d '{"build_type":"workflow", "source":{"branch":"main","path":"/docs"}}'
        res = requests.post(url=url, headers=headers, json=data)
        if 200 <= res.status_code and res.status_code <= 300:
            GinderGit.githubpages_url = res.json()['html_url']
        else:
            raise Exception(f'Could not retrieve GitHub-page url for repo \'{GinderGit.remote_reponame}\' owned by \'{GinderGit.remote_username}\'')
        

    @staticmethod
    def clone_repo(local_dir):
        if not GinderGit.github_user:
            raise Exception('clone_repo() called without registered user')
        if not GinderGit.github_repo:
            raise Exception('clone_repo() called without current github repo')

        import pygit2
        credentials = pygit2.UserPass(GinderPreferences.get_github_token(),'x-oauth-basic')

        # class MyRemoteCallbacks(pygit2.RemoteCallbacks):
        #     def transfer_progress(self, stats):
        #         print(f'{stats.indexed_objects}/{stats.total_objects}')
        # callbacks=MyRemoteCallbacks(credentials=credentials)
        callbacks=pygit2.RemoteCallbacks(credentials=credentials)
        GinderGit.local_repo = pygit2.clone_repository(GinderGit.github_repo.clone_url, local_dir, callbacks=callbacks)

    @staticmethod
    def commit(message:str):
        # https://stackoverflow.com/questions/49458329/create-clone-and-push-to-github-repo-using-pygithub-and-pygit2
        if not GinderGit.github_user:
            raise Exception('commit() called without GitHub user')
        if not GinderGit.local_repo:
            raise Exception('commit() called without local repository')
        import pygit2

        index = GinderGit.local_repo.index
        index.add_all()
        index.write()
        author = pygit2.Signature(GinderGit.github_user.name, GinderGit.github_useremail)
        commiter = pygit2.Signature(GinderGit.github_user.name, GinderGit.github_useremail)
        tree = index.write_tree()
        oid = GinderGit.local_repo.create_commit(GinderGit.local_repo.head.name, author, commiter, message, tree,[GinderGit.local_repo.head.target])

    @staticmethod
    def push():
        if not GinderGit.github_user:
            raise Exception('push() called without GitHub user')
        if not GinderGit.local_repo:
            raise Exception('push() called without local repository')
        if not GinderGit.remote_repo:
            raise Exception('push() called without remote repository')
        import pygit2

        remote = GinderGit.remote_repo
        credentials = pygit2.UserPass(GinderPreferences.get_github_token(),'x-oauth-basic')

        # class MyRemoteCallbacks(pygit2.RemoteCallbacks):
        #     def transfer_progress(self, stats):
        #         print(f'{stats.indexed_objects}/{stats.total_objects}')
        # callbacks=MyRemoteCallbacks(credentials=credentials)
        callbacks=pygit2.RemoteCallbacks(credentials=credentials)
        remote.push([GinderGit.local_repo.head.name], callbacks=callbacks)


    @staticmethod
    def fetch():
        '''Performs a git fetch.'''
        if not GinderGit.github_user:
            raise Exception('fetch() called without GitHub user')
        if not GinderGit.local_repo:
            raise Exception('fetch() called without local repository')
        if not GinderGit.remote_repo:
            raise Exception('fetch() called without remote repository')
        import pygit2

        remote = GinderGit.remote_repo
        credentials = pygit2.UserPass(GinderPreferences.get_github_token(),'x-oauth-basic')

        # class MyRemoteCallbacks(pygit2.RemoteCallbacks):
        #     def transfer_progress(self, stats):
        #         print(f'{stats.indexed_objects}/{stats.total_objects}')
        # callbacks=MyRemoteCallbacks(credentials=credentials)
        callbacks=pygit2.RemoteCallbacks(credentials=credentials)
        remote.fetch(callbacks=callbacks)

    @staticmethod
    def refetch():
        '''Performs a git fetch if the last fetch is not too far away'''
        curtime = time.time()
        if curtime - GinderGit.last_fetch_time > GinderGit.fetch_period:
            GinderGit.fetch()
            GinderGit.last_fetch_time = curtime
        

    # inspired by https://github.com/MichaelBoselowitz/pygit2-examples/blob/master/examples.py#L54
    @staticmethod
    def pull(keep_theirs:bool):
        import pygit2
        remote_name = 'origin'
        branch = 'main'
        for remote in GinderGit.local_repo.remotes:
            if remote.name == remote_name:
                GinderGit.fetch()
                remote_master_id = GinderGit.local_repo.lookup_reference(f'refs/remotes/{remote_name}/{branch}').target
                merge_result, _ = GinderGit.local_repo.merge_analysis(remote_master_id)
                # Up to date, do nothing
                if merge_result & pygit2.GIT_MERGE_ANALYSIS_UP_TO_DATE:
                    return
                # We can just fastforward
                elif merge_result & pygit2.GIT_MERGE_ANALYSIS_FASTFORWARD:
                    GinderGit.local_repo.checkout_tree(GinderGit.local_repo.get(remote_master_id))
                    try:
                        master_ref = GinderGit.local_repo.lookup_reference('refs/heads/%s' % (branch))
                        master_ref.set_target(remote_master_id)
                    except KeyError:
                        GinderGit.local_repo.create_branch(branch, GinderGit.local_repo.get(remote_master_id))
                    GinderGit.local_repo.head.set_target(remote_master_id)
                elif merge_result & pygit2.GIT_MERGE_ANALYSIS_NORMAL:
                    # No file based line-by-line merge. The user has decided to keep "theirs" or "ours"
                    # GinderGit.local_repo.merge(remote_master_id)
                    # if GinderGit.local_repo.index.conflicts is not None:
                    #     for conflict in GinderGit.local_repo.index.conflicts:
                    #         print('Conflicts found in:', conflict[0].path)
                    #     raise AssertionError('Conflicts, ahhhhh!!')
                    favor = pygit2.enums.MergeFavor.THEIRS if keep_theirs else pygit2.enums.MergeFavor.OURS
                    GinderGit.local_repo.merge(remote_master_id, favor=favor)

                    # This should never happen with favor=THEIRS or OURS
                    if GinderGit.local_repo.index.conflicts is not None:
                        raise AssertionError(f'push() encountered conflicts during merge although merged with {favor}.')

                    user = GinderGit.local_repo.default_signature
                    tree = GinderGit.local_repo.index.write_tree()
                    commit = GinderGit.local_repo.create_commit('HEAD',
                                                user,
                                                user,
                                                'Merge!',
                                                tree,
                                                [GinderGit.local_repo.head.target, remote_master_id])
                    # We need to do this or git CLI will think we are still merging.
                    GinderGit.local_repo.state_cleanup()
                else:
                    raise AssertionError('Unknown merge analysis result')



    @staticmethod
    def pending_local_changes() -> int:
        '''Returns the number of changes on the local git repository (file changes not added to the index and/or not committed)'''
        if not GinderGit.local_repo:
            return 0

        index = GinderGit.local_repo.index
        index.read()
        return len(index.diff_to_workdir())

    @staticmethod
    def pending_synch_changes() -> tuple[int, int]:
        '''Returns the number of ahead and behind commits of the local HEAD compared to the remote HEAD (origin).
           The first int of the returned tuple ist the number of commits the local branch is AHEAD of the 
           remote branch - the number of changes that need to be pushed to the remote repo.
           The second int of the returned tuple ist the number of commits the local branch is BEHIND the
           remote branch - the number of changes that need to be pulled from the remote repo.
        '''
        # From answer 3 in https://stackoverflow.com/questions/19930935/how-to-calculate-ahead-or-behind-branchs
        if not GinderGit.local_repo:
            raise Exception('pending_synch_changes() called without local repository')

        upstream_head = GinderGit.local_repo.revparse_single('origin/HEAD')
        local_head    = GinderGit.local_repo.revparse_single('HEAD')
        diff = GinderGit.local_repo.ahead_behind(local_head.id, upstream_head.id)
        return diff


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
        
        # UIUpdate.area.type is either 'TOPBAR' or 'PREFERENCES'
        # try positively asking for that to avoid crashes
        if UIUpdate.area and not UIUpdate.area.type == 'EMPTY':
            # TODO: Make sure the area is still valid
            print(UIUpdate.area.type)
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
    bl_idname = id_for_install_prerequisites_operator
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
    bl_idname = id_for_uninstall_prerequisites_operator
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
    bl_idname = id_for_restart_blender_operator
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
    <title>Ginder authorized ✅</title>
</head>
<body style="font-family: 'Tahoma',sans-serif; margin-top: 5%; margin-left: 5%; margin-right: 5%" >
    <h1>Ginder authorized ✅</h1>
    <p>Congratulations, you successfully registered your installation of <b>Ginder</b>, the GitHub Add-on for Blender.</p>
    <p>You can close this browser tab and continue in Blender.</p>
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
        oa2 = OAuth2Session(ginder_oauth2_client_id, scope="public_repo,user:email")

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
    bl_idname = id_for_register_with_github_operator
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
    bl_idname = id_for_deregister_from_github_operator
    bl_label = "Reset GitHub registration"

    def execute(self, context):
        global preview_collections
        if GinderState.state != GinderState.GITHUB_REGISTERED:
            return {'FINISHED'}
        GinderPreferences.set_github_token('')
        # GinderPreferences.set_github_user('')
        try: del preview_collections['main']['the_avatar_icon'] 
        except: pass
        GinderState.state = GinderState.PREREQ_INSTALLED
        do_url_open(f'https://github.com/settings/connections/applications/{ginder_oauth2_client_id}')
        return {'FINISHED'}

#######################################################################################################
#
#  OPEN Ginder PREFERENCES DIALOG
#
#######################################################################################################

class OpenGinderPrefsOperator(bpy.types.Operator):
    """Open the Ginder Add-On's preferences"""
    bl_idname = id_for_ginder_preferences_operator
    bl_label = "Ginder Preferences"

    def execute(self, context):
        bpy.ops.screen.userpref_show()
        bpy.context.preferences.active_section = 'ADDONS'
        bpy.data.window_managers["WinMan"].addon_search = the_readable_name_of_the_addon
        bpy.data.window_managers["WinMan"].addon_support = {'COMMUNITY'}
        bpy.ops.preferences.addon_show(module=id_for_addon)
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
    """If your browser does not open the Ginder registration page automatically, click this button to copy the GitHub registration link to the clipboard. Afterwards, open your browser and paste the copied link"""
    bl_idname = id_for_copy_registration_link_operator
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
    bl_idname = id_for_addon

    @staticmethod
    def set_github_token(token:str) -> None:
        bpy.context.preferences.addons[id_for_addon].preferences.github_token = token

    @staticmethod
    def get_github_token() -> str:
        return bpy.context.preferences.addons[id_for_addon].preferences.github_token

    github_token: StringProperty(
        name="GitHub Token",
        description="GitHub Access token registered by the user with the Ginder Add-on.",
    ) # type: ignore

    # @staticmethod
    # def set_github_user(user:str) -> None:
    #     bpy.context.preferences.addons[id_for_addon].preferences.github_user = user

    # @staticmethod
    # def get_github_user() -> str:
    #     return bpy.context.preferences.addons[id_for_addon].preferences.github_user

    # github_user: StringProperty(
    #     name="GitHub User",
    #     description="GitHub user registered with the Ginder Add-on.",
    # ) # type: ignore
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
            

        status_text = f'Connected to GitHub as {GinderState.get_user_name()}' if GinderState.state == GinderState.GITHUB_REGISTERED else GinderState.state_description() 
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
        #col.operator(id_for_restart_blender_button, icon='BLENDER')

        match GinderState.state:
            case GinderState.ADDON_INSTALLED:
                col.label(text = status_text)
                col.operator(id_for_install_prerequisites_operator, icon='SCRIPT')

            case GinderState.INSTALLING_PREREQ |GinderState.UNINSTALLING_PREREQ:
                col.label(text = status_text)
                col.progress(factor=UIUpdate.progress, type = 'BAR', text=UIUpdate.message)

            case GinderState.READY_FOR_RESTART:
                col.label(text = status_text)
                col.operator(id_for_restart_blender_operator, icon='QUIT')
                
            case GinderState.PREREQ_INSTALLED:
                col.label(text = status_text)
                col.operator(id_for_register_with_github_operator, icon_value = preview_collections['main']['the_github_icon'].icon_id)
                col.operator(id_for_uninstall_prerequisites_operator, icon='CANCEL')

            case GinderState.REGISTERING_GITHUB:
                col.progress(factor=UIUpdate.progress, type = 'RING', text=status_text)
                col.operator(id_for_copy_registration_link_operator, icon='URL')

            case GinderState.GITHUB_REGISTERED:
                col.label(text = status_text)
                col.operator(id_for_ginder_open_users_github_page_operator, icon='URL')
                col.operator(id_for_deregister_from_github_operator, icon='CANCEL')

            case _:
                col.label(text = 'Undefined State. Try to disable/enable or to remove/re-install Ginder')

        row.template_icon(icon_value = preview_collections['main']['the_ginder_icon_l'].icon_id, scale=1)


#######################################################################################################
#######################################################################################################
#
#  REPOSITORY ACTIONS
#
#######################################################################################################
#######################################################################################################

#######################################################################################################
#
#  CREATE NEW PRESENTATION REPO
#
#######################################################################################################

# inspired by https://blender.stackexchange.com/questions/14738/use-filemanager-to-select-directory-instead-of-file
class CreateNewPresentationRepo(bpy.types.Operator):
    """Create a new presentation repo at your GitHub account and clone it to a selected directory on your local storage"""
    bl_idname = id_for_create_new_presentation_repo_operator
    bl_label = "Create New Repo"
    bl_options = {'REGISTER'}

    # Define this to tell 'fileselect_add' that we want a directoy
    directory: StringProperty(
        name="Local Repository Path",
        description="Local directory where the new presentation repository will be created."
        # subtype='DIR_PATH' is not needed to specify the selection mode.
        # But this will be anyway a directory path.
        )  # type: ignore

    # Filters folders
    filter_folder: BoolProperty(
        default=True,
        options={"HIDDEN"}
        ) # type: ignore


    template_repo: EnumProperty(
        items = [
            ('0', 'FreeDee', 'The standard blender presentaition repository', 0),
            ('1', 'Other Repo', 'This one doesn\'t exist', 1)
        ],
        name="Template",
        description="The template to use for the newly created repository"
    ) # type: ignore

    # test: StringProperty(name="Worscht", description="Grobe oder feine?") # type:ignore

    @classmethod
    def poll(cls, context):
        return GinderState.state == GinderState.GITHUB_REGISTERED

    def execute(self, context):
        # print("Selected repo dir: '" + self.directory + "'")
        if not self.directory:
            report_error('ERROR', f'No directory specified.')
            return {'CANCELLED'}
        if not os.path.isdir(self.directory):
            report_error('ERROR', f'"{str(self.directory)}" is not a directory.')
            return {'CANCELLED'}
        if len(os.listdir(self.directory)) > 0:
            report_error('ERROR', f'"{str(self.directory)}" ist not empty.')
            return {'CANCELLED'}

        repo_name = os.path.basename(os.path.normpath(self.directory))
        try:
            template_username, template_reponame = [('griestopf', 'FreeDee'), ('DEBUG_username', 'DEBUG_reponame')][int(self.template_repo)]
            GinderGit.create_new_repo(repo_name, template_username, template_reponame)
            GinderGit.enable_github_pages()
            # Wait a couple of seconds, otherwise the new GitHub repo is not completely accessible/cloneable from pygit2.
            # directly cloning after creation will lead to incomplete local versions (only .git directory. No other content)
            time.sleep(5)
            GinderGit.clone_repo(self.directory)
        except Exception as ex:
            report_error('ERROR', f'Error while creating repository "{str(self.directory)}": \n{str(ex)}')
            return {'CANCELLED'}

        return {'FINISHED'}

    def draw(self, context):
        layout = self.layout
        layout.label(text='Select an empty directory')
        layout.label(text='or create one!')
        layout.prop(self, 'template_repo')

    def invoke(self, context, event):
        # Open browser, take reference to 'self' read the path to selected
        # file, put path in predetermined self fields.
        # See: https://docs.blender.org/api/current/bpy.types.WindowManager.html#bpy.types.WindowManager.fileselect_add
        context.window_manager.fileselect_add(self)

        # Tells Blender to hang on for the slow user input
        return {'RUNNING_MODAL'}

#######################################################################################################
#
#  OPEN User's GitHub Account
#
#######################################################################################################

class OpenUsersGitHubProfileOperator(bpy.types.Operator):
    """Open the current user's GitHub user profile"""
    bl_idname = id_for_ginder_open_users_github_page_operator
    bl_label = "Open GitHub user profile"


    @classmethod
    def poll(cls, context):
        return GinderState.state == GinderState.GITHUB_REGISTERED

    def execute(self, context):
        # Try to connnect to GitHub using the token passed to us
        if not GinderState.state == GinderState.GITHUB_REGISTERED:
            report_error('ERROR', 'Ginder not registered with GitHub. Could not open user\'s GitHub page.')
            return {'CANCELLED'}

        try:
            user = GinderGit.github_user
            do_url_open(user.html_url)
            return {'FINISHED'}
        except:
            report_error('ERROR', 'Could not log-on to GitHub.')
            return {'CANCELLED'}


#######################################################################################################
#
#  OPEN CURRENT REPOs GITHUB PAGE
#
#######################################################################################################

class OpenReposGitHubPageOperator(bpy.types.Operator):
    """Open the current presentation repo's GitHub Page"""
    bl_idname = id_for_ginder_open_repos_github_page_operator
    bl_label = "Open GitHub-Pages page"

    @classmethod
    def poll(cls, context):
        return GinderState.state == GinderState.GITHUB_REGISTERED and GinderGit.githubpages_url

    def execute(self, context):
        if not (GinderState.state == GinderState.GITHUB_REGISTERED and GinderGit.githubpages_url):
            report_error('ERROR', 'Ginder not registered with GitHub. Could not open user\'s GitHub page.')
            return {'CANCELLED'}


        try:
            # Add a minimal pseudo query string with changing keys/values to keep the CDN delivering
            # the generated GitHub page content from too much caching. 
            # According to https://stackoverflow.com/questions/24851824/how-long-does-it-take-for-github-page-to-show-changes-after-changing-index-html
            # this should work, but not sure if it really does.
            if GinderGit.local_repo:
                local_head    = GinderGit.local_repo.revparse_single('HEAD')
                version = local_head.hex[:4]
                query_string = f'?v={version}'
            else:
                query_string = f'?{random.choice(string.ascii_letters)}={random.choice(string.digits)}'
            do_url_open(GinderGit.githubpages_url + query_string)
            return {'FINISHED'}
        except Exception as ex:
            report_error('ERROR', f'Could not Open GitHubPage of {GinderGit.remote_reponame}.\n{ex}')
            return {'CANCELLED'}


#######################################################################################################
#
#  COMMIT TO REPO 
#
#######################################################################################################

class CommitToRepoOperator(bpy.types.Operator):
    """Commit changes in all files in the repo directory to the local repository"""
    bl_idname = id_for_commit_to_repo_operator
    bl_label = "Commit Changes to Repo"

    @classmethod
    def poll(cls, context):
        return GinderGit.local_repo and (GinderGit.pending_local_changes() > 0 or bpy.data.is_dirty)

    def execute(self, context):
        if not (GinderGit.local_repo and (GinderGit.pending_local_changes() > 0 or bpy.data.is_dirty)):
            report_error('ERROR', 'Cannot commit to repo.')
            return {'CANCELLED'}
        try:
            if bpy.data.is_dirty:
                bpy.ops.wm.save_mainfile()
            print(f'Commit to {GinderGit.local_repo.path}')
            commit_message = f'{bpy.context.window.workspace.name} edits on {bpy.context.object.name} in {bpy.path.basename(bpy.context.blend_data.filepath)}'
            GinderGit.commit(commit_message)
            return {'FINISHED'}
        except Exception as ex:
            report_error('ERROR', f'Could not Commit to {GinderGit.local_repo.path}.\n{ex}')
            return {'CANCELLED'}


#######################################################################################################
#
#  PUSH TO REMOTE REPO 
#
#######################################################################################################

class PushToRemoteOperator(bpy.types.Operator):
    """Push all committed changes to the remote repository. This option is only available if there are no local uncommitted changes and the current file is saved. Consider reverting or saving the current file."""
    bl_idname = id_for_push_to_remote_operator
    bl_label = "Push Changes to Remote Repo"

    @classmethod
    def poll(cls, context):
        numberofchanges = GinderGit.pending_local_changes()
        if not (GinderGit.github_user and GinderGit.local_repo and GinderGit.remote_repo and numberofchanges == 0 and not bpy.data.is_dirty):
            return False
        GinderGit.refetch()
        (topush, topull) = GinderGit.pending_synch_changes()        
        return topush > 0 and topull == 0

    def execute(self, context):
        if not (GinderGit.github_user and GinderGit.local_repo and GinderGit.remote_repo):
            report_error('ERROR', 'Cannot push changes to remote repo.')
            return {'CANCELLED'}
        try:
            GinderGit.refetch()
            (topush, topull) = GinderGit.pending_synch_changes()
            if topush > 0:
                GinderGit.push()
            if topull > 0:
                report_error('ERROR', f'Pushing to {GinderGit.remote_reponame} with {topull} pulls open.')
            return {'FINISHED'}
        except Exception as ex:
            report_error('ERROR', f'Could not push to {GinderGit.remote_reponame}.\n{ex}')
            return {'CANCELLED'}


#######################################################################################################
#
#  PULL FROM REMOTE REPO 
#
#######################################################################################################

class PullFromRemoteOperator(bpy.types.Operator):
    """Pull ahead changes from the remote repository. This option is only available if there are no local uncommitted changes and the current file is saved. Consider reverting or saving the current file."""
    bl_idname = id_for_pull_from_remote_operator
    bl_label = "Pull Changes from Remote Repo"

    @classmethod
    def poll(cls, context):
        numberofchanges = GinderGit.pending_local_changes()
        if not (GinderGit.github_user and GinderGit.local_repo and GinderGit.remote_repo and numberofchanges == 0 and not bpy.data.is_dirty):
            return False
        GinderGit.refetch()
        (topush, topull) = GinderGit.pending_synch_changes()        
        return topush == 0 and topull > 0

    def execute(self, context):
        numberofchanges = GinderGit.pending_local_changes()
        if not (GinderGit.github_user and GinderGit.local_repo and GinderGit.remote_repo and numberofchanges == 0 and not bpy.data.is_dirty):
            report_error('ERROR', 'Cannot pull changes from remote repo.')
            return {'CANCELLED'}
        try:
            GinderGit.refetch()
            (topush, topull) = GinderGit.pending_synch_changes()
            if topull > 0:
                GinderGit.pull(False)
                bpy.ops.wm.revert_mainfile()
            if topush > 0:
                report_error('ERROR', f'Pulling from {GinderGit.remote_reponame} with {topush} pushes open.')
            return {'FINISHED'}
        except Exception as ex:
            report_error('ERROR', f'Could pull changes from {GinderGit.remote_reponame}.\n{ex}')
            return {'CANCELLED'}


#######################################################################################################
#
#  Merge Theirs
#
#######################################################################################################

class MergeTheirsOperator(bpy.types.Operator):
    """Merge the changes on the remote repository with those on the local repository. Prefer keeping the remote changes in case of conflicts. This option is only available if there are no local uncommitted changes and the current file is saved. Consider reverting or saving the current file."""
    bl_idname = id_for_merge_theirs_operator
    bl_label = "Merge Changes and Keep Remote Versions for Conflicts"
    @classmethod
    def poll(cls, context):
        numberofchanges = GinderGit.pending_local_changes()
        if not (GinderGit.github_user and GinderGit.local_repo and GinderGit.remote_repo and numberofchanges == 0 and not bpy.data.is_dirty):
            return False
        GinderGit.refetch()
        (topush, topull) = GinderGit.pending_synch_changes()        
        return topush > 0 and topull > 0

    def execute(self, context):
        numberofchanges = GinderGit.pending_local_changes()
        if not (GinderGit.github_user and GinderGit.local_repo and GinderGit.remote_repo and numberofchanges == 0 and not bpy.data.is_dirty):
            report_error('ERROR', 'Cannot merge changes with remote repo.')
            return {'CANCELLED'}
        try:
            GinderGit.refetch()
            (topush, topull) = GinderGit.pending_synch_changes()
            if topull > 0:
                GinderGit.pull(True)
                bpy.ops.wm.revert_mainfile()
            if topush > 0:
                GinderGit.push()
            return {'FINISHED'}
        except Exception as ex:
            report_error('ERROR', f'Could merge changes with {GinderGit.remote_reponame}.\n{ex}')
            return {'CANCELLED'}


#######################################################################################################
#
#  Merge Ours
#
#######################################################################################################

class MergeOursOperator(bpy.types.Operator):
    """Merge the changes on the remote repository with those on the local repository. Prefer keeping your local changes in case of conflicts. This option is only available if there are no local uncommitted changes and the current file is saved. Consider reverting or saving the current file."""
    bl_idname = id_for_merge_ours_operator
    bl_label = "Merge Changes and Keep Local Versions for Conflicts"
    @classmethod
    def poll(cls, context):
        numberofchanges = GinderGit.pending_local_changes()
        if not (GinderGit.github_user and GinderGit.local_repo and GinderGit.remote_repo and numberofchanges == 0 and not bpy.data.is_dirty):
            return False
        GinderGit.refetch()
        (topush, topull) = GinderGit.pending_synch_changes()        
        return topush > 0 and topull > 0

    def execute(self, context):
        numberofchanges = GinderGit.pending_local_changes()
        if not (GinderGit.github_user and GinderGit.local_repo and GinderGit.remote_repo and numberofchanges == 0 and not bpy.data.is_dirty):
            report_error('ERROR', 'Cannot merge changes with remote repo.')
            return {'CANCELLED'}
        try:
            GinderGit.refetch()
            (topush, topull) = GinderGit.pending_synch_changes()
            if topull > 0:
                GinderGit.pull(False)
                bpy.ops.wm.revert_mainfile()
            if topush > 0:
                GinderGit.push()
            return {'FINISHED'}
        except Exception as ex:
            report_error('ERROR', f'Could merge changes with {GinderGit.remote_reponame}.\n{ex}')
            return {'CANCELLED'}


#######################################################################################################
#
#  Ginder -> Synchronize with GitHub MENU
#
#######################################################################################################

class SynchronizeMenu(bpy.types.Menu):
    bl_label = 'Synchronize Menu'
    bl_idname = 'Ginder_Synchronize_menu'

    def draw(self, context):
        layout = self.layout

        layout.operator(id_for_merge_theirs_operator, icon_value = preview_collections['main']["the_merge_theirs_icon"].icon_id)
        layout.operator(id_for_merge_ours_operator, icon_value = preview_collections['main']["the_merge_ours_icon"].icon_id)



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

        numberofchanges = GinderGit.pending_local_changes()
        if  GinderGit.local_repo and (bpy.data.is_dirty or numberofchanges > 0):
            if (bpy.data.is_dirty):
                if numberofchanges == 0:
                    numberofchanges += 1
                layout.operator(id_for_commit_to_repo_operator, text=f'Save and Commit {numberofchanges} Change{"s" if numberofchanges > 1 else ""} to {GinderGit.local_reponame}', icon='CHECKMARK')
            else:
                layout.operator(id_for_commit_to_repo_operator, text=f'Commit {numberofchanges} Change{"s" if numberofchanges > 1 else ""} to {GinderGit.local_reponame}', icon='CHECKMARK')
        else:
            layout.operator(id_for_commit_to_repo_operator, icon='CHECKMARK')

        # Only show the push/pull/sync menu item if there is a local repo and a remote repo and there. Show the correct option based on the ahead/behind status even if there are local changes.
        # In case of local commits or an unsaved file, the push/pull/sync options will be disabled by the respective operators' poll methods.
        if GinderGit.github_user and GinderGit.local_repo and GinderGit.remote_repo: # and numberofchanges == 0 and not bpy.data.is_dirty
            GinderGit.refetch()
            (topush, topull) = GinderGit.pending_synch_changes()
            if topush > 0 and topull > 0:
                # Show the sync submenu
                text = f'Synchronize {str(topull)}↓ and {str(topush)}↑ Commits With {GinderGit.remote_reponame}'
                layout.menu('Ginder_Synchronize_menu', text=text, icon='FILE_REFRESH')
            elif topull > 0:
                text = f'Pull {str(topull)} Commit{"s" if topull > 1 else ""} From {GinderGit.remote_reponame}'
                layout.operator(id_for_pull_from_remote_operator, text=text, icon='SORT_ASC')
            elif topush > 0:
                text = f'Push {str(topush)} Commit{"s" if topush > 1 else ""} To {GinderGit.remote_reponame}'
                layout.operator(id_for_push_to_remote_operator, text=text, icon='SORT_DESC')
            else: # no changes to push or pull
                layout.operator(id_for_push_to_remote_operator, text = f"Synchronize Changes With {GinderGit.remote_reponame}", icon='FILE_REFRESH') # should appear disabled
        else:
            layout.operator(id_for_push_to_remote_operator, text = f"Synchronize Changes With Remote Repo", icon='FILE_REFRESH') # should appear disabled


        if GinderGit.remote_reponame:
            # layout.label(f'Repo {GinderGit.remote_reponame} on GitHub')
            layout.operator(id_for_ginder_open_repos_github_page_operator, text=f'Open {GinderGit.remote_reponame}\'s GitHub-Pages page', icon='URL')
        else:
            layout.operator(id_for_ginder_open_repos_github_page_operator, icon='URL')

        # if GinderState.state == GinderState.GITHUB_REGISTERED:
        #     layout.operator(id_for_ginder_open_users_github_page_operator, text=f'Open {GinderState.get_login_name()}\'s GitHub user profile', icon='URL')
        # else:
        #     layout.operator(id_for_ginder_open_users_github_page_operator, icon='URL')

        layout.operator(id_for_create_new_presentation_repo_operator, icon = 'NEWFOLDER')

        layout.operator(id_for_ginder_preferences_operator, icon='PREFERENCES')


#######################################################################################################

def draw_ginder_menu(self, context):
    layout = self.layout
    if GinderGit.local_reponame:
        text = f'{GinderGit.local_reponame} - Ginder'
    else: 
        text = 'Ginder'
    layout.menu(GinderMenu.bl_idname, text = text, icon_value = preview_collections['main']["the_ginder_icon"].icon_id)


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
    pcoll.load('the_merge_theirs_icon', os.path.join(my_icons_dir, 'merge_theirs.png'), 'IMAGE')
    pcoll.load('the_merge_ours_icon', os.path.join(my_icons_dir, 'merge_ours.png'), 'IMAGE')

    preview_collections['main'] = pcoll

    bpy.utils.register_class(RegisterWithGitHubOperator)
    bpy.utils.register_class(DeregisterFromGitHubOperator)
    bpy.utils.register_class(InstallPrerequisitesOperator)
    bpy.utils.register_class(UninstallPrerequisitesOperator)
    bpy.utils.register_class(RestartBlenderOperator)
    bpy.utils.register_class(CopyRegistrationLinkOperator)
    bpy.utils.register_class(GinderPreferences)
    bpy.utils.register_class(OpenGinderPrefsOperator)
    bpy.utils.register_class(OpenUsersGitHubProfileOperator)
    bpy.utils.register_class(OpenReposGitHubPageOperator)
    bpy.utils.register_class(CreateNewPresentationRepo)
    bpy.utils.register_class(CommitToRepoOperator)
    bpy.utils.register_class(PushToRemoteOperator)
    bpy.utils.register_class(PullFromRemoteOperator)
    bpy.utils.register_class(MergeTheirsOperator)
    bpy.utils.register_class(MergeOursOperator)
    bpy.utils.register_class(SynchronizeMenu)
    bpy.utils.register_class(GinderMenu)
    bpy.types.TOPBAR_MT_file.prepend(draw_ginder_menu)
    bpy.context.preferences.use_preferences_save = True # see https://blender.stackexchange.com/questions/157677/add-on-preferences-auto-saving-bug
    GinderState.install_post_load_handler()

    # Check once on startup
    UIUpdate.start_pulse()
    GinderState.init()

def unregister():
    UIUpdate.stop_pulse()
    bpy.types.TOPBAR_MT_file.remove(draw_ginder_menu)
    bpy.utils.unregister_class(GinderMenu)
    bpy.utils.unregister_class(SynchronizeMenu)
    bpy.utils.unregister_class(MergeOursOperator)
    bpy.utils.unregister_class(MergeTheirsOperator)
    bpy.utils.unregister_class(PullFromRemoteOperator)
    bpy.utils.unregister_class(PushToRemoteOperator)
    bpy.utils.unregister_class(CommitToRepoOperator)
    bpy.utils.unregister_class(CreateNewPresentationRepo)
    bpy.utils.unregister_class(OpenReposGitHubPageOperator)
    bpy.utils.unregister_class(OpenUsersGitHubProfileOperator)
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
