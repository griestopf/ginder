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
the_unique_name_of_the_deregister_with_github_button = "ginder.deregister_with_github"
the_unique_name_of_the_install_prerequisites_button = "ginder.install_prerequisites"
the_unique_name_of_the_uninstall_prerequisites_button = "ginder.uninstall_prerequisites"
the_unique_name_of_the_restart_blender_button = "ginder.restart_blender"
the_unique_name_of_the_ginder_preferences_button = "ginder.preferences"


#######################################################################################################

def connected_to_internet(url='https://www.example.com/', timeout=5):
    try:
        _ = requests.head(url, timeout=timeout)
        return True
    except requests.ConnectionError:
        pass
    return False

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
  

def install_prerequisites() -> bool:
    check_prerequisites()
    try:
        n = len(ginder_prerequisites) - sum(ginder_prerequisites.values())
        n += 1  # For Pip
        i=1.0
        # deprecated as of 2.91: pybin = bpy.app.binary_path_python. Instead use 
        pybin = sys.executable

        Progress.milestone(i/n, 'Installing/Updating pip', 2)
        ensurepip.bootstrap()
        subprocess.check_call([pybin, '-m', 'pip', 'install', '--upgrade', 'pip'])

        if not ginder_prerequisites['pygit2']:
            i += 1
            Progress.milestone(i/n, 'Installing pygit2', 2)
            subprocess.check_call([pybin, '-m', 'pip', 'install', 'pygit2'])
        if not ginder_prerequisites['github']:
            i += 1
            Progress.milestone(i/n, 'Installing PyGithub', 2)
            subprocess.check_call([pybin, '-m', 'pip', 'install', 'PyGithub'])
        if not ginder_prerequisites['requests_oauthlib']:
            i += 1
            Progress.milestone(i/n, 'Installing requests-oauthlib', 2)
            subprocess.check_call([pybin, '-m', 'pip', 'install', 'requests-oauthlib'])
    except Exception as ex:
        run_in_main_thread(functools.partial(report_error, 'ERROR Installing Ginder Prerequisites', f'Could not pip install one or more modules required by Ginder\n{str(ex)}'))
        return False
    check_prerequisites()
    if ginder_prerequisites['pygit2'] and ginder_prerequisites['github'] and ginder_prerequisites['requests_oauthlib']:
        GinderState.state = GinderState.PREREQ_INSTALLED
    else:
        GinderState.state = GinderState.READY_FOR_RESTART
    return True


def uninstall_prerequisites() -> bool:
    try:
        n = 3.0
        i=1.0
        # deprecated as of 2.91: pybin = bpy.app.binary_path_python. Instead use 
        pybin = sys.executable

        Progress.milestone(i/n, 'Uninstalling requests-oauthlib', 2)
        subprocess.check_call([pybin, '-m', 'pip', 'uninstall', '-y', 'requests-oauthlib'])

        i += 1
        Progress.milestone(i/n, 'Uninstalling PyGithub', 2)
        subprocess.check_call([pybin, '-m', 'pip', 'uninstall', '-y', 'PyGithub'])

        i += 1
        Progress.milestone(i/n, 'Uninstalling pygit2', 2)
        subprocess.check_call([pybin, '-m', 'pip', 'uninstall', '-y', 'pygit2'])
    except Exception as ex:
        run_in_main_thread(functools.partial(report_error, 'ERROR Uninstalling Ginder Prerequisites', f'Could not pip uninstall one modules\n{str(ex)}'))
        return False
    check_prerequisites()
    if not (ginder_prerequisites['pygit2'] and ginder_prerequisites['github'] and ginder_prerequisites['requests_oauthlib']):
        GinderState.state = GinderState.PREREQ_INSTALLED
    else:
        GinderState.state = GinderState.READY_FOR_RESTART
    return True


#######################################################################################################

class GinderState:
    UNDEFINED = -1
    ADDON_INSTALLED = 0
    INSTALLING_PREREQ = 1
    UNINSTALLING_PREREQ = 2
    READY_FOR_RESTART = 3
    PREREQ_INSTALLED = 4
    REGISTERING_GITHUB = 5
    GITHUB_REGISTERED = 6
    LAST_STATE = 7

    state = UNDEFINED

    state_descriptions = [
        "Necessary python modules not installed", 
        "Installing necessary python modules", 
        "Uninstalling python modules", 
        "Blender needs to be restarted", 
        "Ready to register with GitHub",
        "Finish GitHub registration process in browser",
        "Ready"
        ]

    def state_description() -> str:
        if 0 <= GinderState.state and GinderState.state < GinderState.LAST_STATE:
            return GinderState.state_descriptions[GinderState.state]
        return 'Undefined'

    @staticmethod
    def init():
        check_prerequisites()
        if False: # TODO: check for user token
            GinderState.state = GinderState.GITHUB_REGISTERED
        elif ginder_prerequisites['pygit2'] and ginder_prerequisites['github'] and ginder_prerequisites['requests_oauthlib']:
            GinderState.state = GinderState.PREREQ_INSTALLED
        else:
            GinderState.state = GinderState.ADDON_INSTALLED
        return GinderState.state

GinderState.init()

#######################################################################################################


#get the folder path for the .py file containing this function
def get_path():
    return os.path.dirname(os.path.realpath(__file__))


def report_error(header: str, msg: str):
    ShowMessageBox(msg, header, 'ERROR')
    print(header + ": " + msg)


#######################################################################################################

def ShowMessageBox(message = "", title = "Message Box", icon = 'INFO'):

    def draw(self, context):
        self.layout.label(text=message)

    bpy.context.window_manager.popup_menu(draw, title = title, icon = icon)


#######################################################################################################


execution_queue = queue.Queue()

# This function can safely be called in another thread.
# The function will be executed when the timer runs the next time.
def run_in_main_thread(function):
    execution_queue.put(function)


def execute_queued_functions():
    while not execution_queue.empty():
        function = execution_queue.get()
        function()
    return 1.0

bpy.app.timers.register(execute_queued_functions)

#######################################################################################################

class Progress:
    progress:float = 0
    duration:float = 0
    endat:float = 0
    startat:float = 0
    bps:float = 0.05
    speed:float = 0
    message:str = ''
    stop=True

    @staticmethod
    def init(area:bpy.types.Area, bps:float = 0.05, msg:str = ''):
        Progress.progress = 0
        Progress.duration = 0
        Progress.endat = 0
        Progress.startat = 0
        Progress.bps = bps
        Progress.message = msg
        Progress.stop = False
        bpy.app.timers.register(functools.partial(Progress.pulse, area))

    @staticmethod
    def milestone(endat:float, msg:str=None, duration:float = 3):
        if msg:
            Progress.message = msg
        Progress.startat = Progress.progress
        Progress.duration = duration
        Progress.endat = endat
        Progress.speed = (endat - Progress.startat) / duration

    @staticmethod
    def pulse(area : bpy.types.Area):
        if Progress.stop:
            return None
        Progress.progress += Progress.speed * Progress.bps
        if Progress.progress >= Progress.startat + 0.5*(Progress.endat - Progress.startat):
            Progress.speed *= 0.5
            Progress.startat = Progress.progress
        area.tag_redraw()
        return Progress.bps

#######################################################################################################

class InstallPrerequisitesOperator(bpy.types.Operator):
    """Download and install python modules required by this Add-on"""
    bl_idname = the_unique_name_of_the_install_prerequisites_button
    bl_label = "Install Prerequisites"

    def execute(self, context):
        if GinderState.state != GinderState.ADDON_INSTALLED:
            report_error('Ginder installation', 'The AddOn is in an unexpected state')
            return {'CANCELLED'}

        Progress.init(context.area)
        install_prereq_thread = threading.Thread(target=install_prerequisites)
        install_prereq_thread.start()
        GinderState.state = GinderState.INSTALLING_PREREQ
        return {'FINISHED'}


#######################################################################################################

class UninstallPrerequisitesOperator(bpy.types.Operator):
    """Remove python modules installed by this Add-on"""
    bl_idname = the_unique_name_of_the_uninstall_prerequisites_button
    bl_label = "Uninstall Prerequisites"

    def execute(self, context):
        if GinderState.state != GinderState.PREREQ_INSTALLED:
            report_error('Ginder installation', 'The AddOn is in an unexpected state')
            return {'CANCELLED'}

        Progress.init(context.area)
        install_prereq_thread = threading.Thread(target=uninstall_prerequisites)
        install_prereq_thread.start()
        GinderState.state = GinderState.UNINSTALLING_PREREQ
        return {'FINISHED'}


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

class DeregisterWithGitHubOperator(bpy.types.Operator):
    """De-register Ginder (this Add-on) from your GitHub user account."""
    bl_idname = the_unique_name_of_the_deregister_with_github_button
    bl_label = "Deregister with GitHub"

    def execute(self, context):#
        ## Do this: https://docs.github.com/en/rest/apps/oauth-applications?apiVersion=2022-11-28#delete-an-app-token
        report_error('Test', self.bl_label)
        return {'FINISHED'}

#######################################################################################################

class RegisterWithGitHubOperator(bpy.types.Operator):
    """Register with your user name at GitHub and allow Ginder (this Add-on) to access your public repositories"""
    bl_idname = the_unique_name_of_the_register_with_github_button
    bl_label = "Register with GitHub"

    def execute(self, context):
        report_error('Test', 'Register with GitHub')
        return {'FINISHED'}

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

class GinderPreferences(AddonPreferences):
    # this must match the add-on name, use '__package__'
    # when defining this in a submodule of a python package.
    bl_idname = the_unique_name_of_the_addon

    github_user: StringProperty(
        name="GitHub User",
        description="GitHub User registered with the Ginder Add-on.",
        # subtype='FILE_PATH',
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

        if GinderState.state == GinderState.UNDEFINED:
            GinderState.init()
            
        row = layout.row()
        row.scale_y = 1
        row.label(text = "Ginder", icon_value = preview_collections["main"]["the_ginder_icon"].icon_id)
        row.label(text = f'State: {GinderState.state_description()}')
        row = layout.row()
        row.scale_y = 1.5

        if GinderState.state == GinderState.ADDON_INSTALLED:
            row.operator(the_unique_name_of_the_install_prerequisites_button, icon="SCRIPT")

        elif GinderState.state == GinderState.INSTALLING_PREREQ or GinderState.state == GinderState.UNINSTALLING_PREREQ:
            row.progress(factor=Progress.progress, type = 'BAR', text=Progress.message)

        elif GinderState.state == GinderState.READY_FOR_RESTART:
            row.operator(the_unique_name_of_the_restart_blender_button, icon="BLENDER")
            
        elif GinderState.state == GinderState.PREREQ_INSTALLED:
            row.operator(the_unique_name_of_the_register_with_github_button, icon_value = preview_collections["main"]["the_github_icon"].icon_id)
            row = layout.row()
            row.scale_y = 1
            row.operator(the_unique_name_of_the_uninstall_prerequisites_button, icon="SCRIPT")

        elif GinderState.state == GinderState.GITHUB_REGISTERED:
            row.prop(self, "github_user")

# See https://blenderartists.org/t/best-practice-for-addon-key-bindings-own-preferences-or-blenders/1416828
# to add a button as an operator



#######################################################################################################

class GinderMenu(bpy.types.Menu):
    bl_label = "Ginder Menu"
    bl_idname = "FILE_MT_ginder_menu"

    def draw(self, context):
        layout = self.layout

        layout.operator("wm.open_mainfile")
        layout.operator("wm.save_as_mainfile").copy = True
        layout.operator(the_unique_name_of_the_ginder_preferences_button)


#######################################################################################################

def draw_ginder_menu(self, context):
    layout = self.layout
    #pcoll = preview_collections["main"]
    #ginder_icon = pcoll["the_ginder_icon"]
    layout.menu(GinderMenu.bl_idname, text = 'Ginder - darepo', icon_value = preview_collections["main"]["the_ginder_icon"].icon_id)


# We can store multiple preview collections here,
# however in this example we only store "main"
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
    my_icons_dir = os.path.join(os.path.dirname(__file__), "icons")

    # load a preview thumbnail of a file and store in the previews collection
    pcoll.load("the_github_icon", os.path.join(my_icons_dir, "github_icon.png"), 'IMAGE')
    pcoll.load("the_ginder_icon", os.path.join(my_icons_dir, "ginder_icon_w.png"), 'IMAGE')

    preview_collections["main"] = pcoll


    bpy.utils.register_class(RegisterWithGitHubOperator)
    bpy.utils.register_class(DeregisterWithGitHubOperator)
    bpy.utils.register_class(InstallPrerequisitesOperator)
    bpy.utils.register_class(UninstallPrerequisitesOperator)
    bpy.utils.register_class(RestartBlenderOperator)
    bpy.utils.register_class(GinderPreferences)
    bpy.utils.register_class(OpenGinderPrefsOperator)
    bpy.utils.register_class(GinderMenu)
    bpy.types.TOPBAR_MT_file.prepend(draw_ginder_menu)

    # Check once on startup
    GinderState.init()


def unregister():
    bpy.types.TOPBAR_MT_file.remove(draw_ginder_menu)
    bpy.utils.unregister_class(GinderMenu)
    bpy.utils.unregister_class(OpenGinderPrefsOperator)
    bpy.utils.unregister_class(GinderPreferences)
    bpy.utils.unregister_class(RestartBlenderOperator)
    bpy.utils.unregister_class(UninstallPrerequisitesOperator)
    bpy.utils.unregister_class(InstallPrerequisitesOperator)
    bpy.utils.unregister_class(DeregisterWithGitHubOperator)
    bpy.utils.unregister_class(RegisterWithGitHubOperator)

    # Custom icon deregistration
    for pcoll in preview_collections.values():
         bpy.utils.previews.remove(pcoll)
    preview_collections.clear()

if __name__ == "__main__":
    register()
