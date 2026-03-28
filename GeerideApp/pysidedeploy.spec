[app]
title = SkiSense
project_dir = C:\Users\risko\Desktop\GeerideApp
input_file = main.py
exec_directory = C:\Users\risko\Desktop\GeerideApp\dist
project_file = 
icon = C:\Users\risko\Desktop\GeerideApp\assets\geeride_icon.ico

[python]
python_path = C:\Users\risko\AppData\Local\Python\pythoncore-3.14-64\python.exe
packages = Nuitka==4.0.7
android_packages = buildozer==1.5.0,cython==0.29.33

[qt]
qml_files = 
excluded_qml_plugins = 
modules = Core,Gui,Multimedia,MultimediaWidgets,WebEngineWidgets,Widgets
plugins = 

[android]
wheel_pyside = 
wheel_shiboken = 
plugins = 

[nuitka]
macos.permissions = 
mode = onefile
extra_args = --quiet --noinclude-qt-translations --windows-console-mode=disable --assume-yes-for-downloads --include-data-dir=assets=./assets

[buildozer]
mode = debug
recipe_dir = 
jars_dir = 
ndk_path = 
sdk_path = 
local_libs = 
arch = 

