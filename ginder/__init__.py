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
import ensurepip
import subprocess
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
the_unique_name_of_the_install_prerequisites_button = "ginder.install_prerequisites"

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
  

# Check once on startup
check_prerequisites()

def install_prerequisites() -> bool:
    check_prerequisites()
    try:
        ensurepip.bootstrap()
        # deprecated as of 2.91: pybin = bpy.app.binary_path_python. Instead use 
        pybin = sys.executable
        if not ginder_prerequisites['pygit2']:
            subprocess.check_call([pybin, '-m', 'pip', 'install', 'pygit2'])
        if not ginder_prerequisites['github']:
            subprocess.check_call([pybin, '-m', 'pip', 'install', 'PyGithub'])
        if not ginder_prerequisites['requests_oauthlib']:
            subprocess.check_call([pybin, '-m', 'pip', 'install', 'requests-oauthlib'])
    except Exception as ex:
        report_error('ERROR Installing Ginder Prerequisites', f'Could not pip install one or more modules required by Ginder\n{str(ex)}')
        return False
    check_prerequisites()
    return 


#######################################################################################################

class GinderState(Enum):
    ADDON_INSTALLED = 0
    PREREQ_INSTALLED = 1
    GITHUB_REGISTERED = 2

def get_ginder_state():
    if False: # TODO: check for user token
        return GinderState.GITHUB_REGISTERED
    if ginder_prerequisites['pygit2'] and ginder_prerequisites['github'] and ginder_prerequisites['requests_oauthlib']:
        return GinderState.PREREQ_INSTALLED
    return GinderState.ADDON_INSTALLED

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

class RegisterWithGitHubOperator(bpy.types.Operator):
    """Register with your user name at GitHub and allow Ginder (this Add-On) to access your public repositories"""
    bl_idname = the_unique_name_of_the_register_with_github_button
    bl_label = "Register with GitHub"

    def execute(self, context):
        report_error('Test', 'Register with GitHub')
        return {'FINISHED'}


#######################################################################################################

class InstallPrerequisitesOperator(bpy.types.Operator):
    """Download and install python modules required by this Add-On"""
    bl_idname = the_unique_name_of_the_install_prerequisites_button
    bl_label = "Install Prerequisites"

    def execute(self, context):
        report_error('Test', 'Install Prereqs')
        return {'FINISHED'}



#######################################################################################################


class GinderPreferences(AddonPreferences):
    # this must match the add-on name, use '__package__'
    # when defining this in a submodule of a python package.
    bl_idname = the_unique_name_of_the_addon

    github_user: StringProperty(
        name="GitHub User",
        description="GitHub User registered with the Ginder Add-On.",
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

        state = get_ginder_state()

        if state == GinderState.ADDON_INSTALLED:
            row = layout.row()
            row.scale_y = 1.5
            row.operator(the_unique_name_of_the_install_prerequisites_button, icon="SCRIPT")
            row.progress(factor=0.7, type = 'RING', text = "Updating")

        elif state == GinderState.PREREQ_INSTALLED:
            pcoll = preview_collections["main"]
            github_icon = pcoll["the_github_icon"]        
            layout.operator(the_unique_name_of_the_register_with_github_button, icon_value=github_icon.icon_id)

        elif state == GinderState.GITHUB_REGISTERED:
            layout.prop(self, "github_user")

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


#######################################################################################################

def draw_ginder_menu(self, context):
    layout = self.layout
    pcoll = preview_collections["main"]
    ginder_icon = pcoll["the_ginder_icon"]
    layout.menu(GinderMenu.bl_idname, text='Ginder - darepo', icon_value=ginder_icon.icon_id)

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
    bpy.utils.register_class(InstallPrerequisitesOperator)
    bpy.utils.register_class(GinderPreferences)
    bpy.utils.register_class(GinderMenu)
    bpy.types.TOPBAR_MT_file.prepend(draw_ginder_menu)

    # Check once on startup
    check_prerequisites()


def unregister():
    bpy.types.TOPBAR_MT_file.remove(draw_ginder_menu)
    bpy.utils.unregister_class(GinderMenu)
    bpy.utils.unregister_class(GinderPreferences)
    bpy.utils.unregister_class(InstallPrerequisitesOperator)
    bpy.utils.unregister_class(RegisterWithGitHubOperator)

    # Custom icon deregistration
    for pcoll in preview_collections.values():
         bpy.utils.previews.remove(pcoll)
    preview_collections.clear()

if __name__ == "__main__":
    register()
