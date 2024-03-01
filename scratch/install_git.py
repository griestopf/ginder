import bpy
import ensurepip
import subprocess
ensurepip.bootstrap()
pybin = bpy.app.binary_path_python
subprocess.check_call([pybin, '-m', 'pip', 'install', 'pygit2'])
subprocess.check_call([pybin, '-m', 'pip', 'install', 'PyGithub'])
