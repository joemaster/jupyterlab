# coding: utf-8
"""A tornado based Jupyter lab server."""

# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import json
import os
import sys

from jupyter_core.application import JupyterApp, base_aliases
from jupyterlab_server import slugify, WORKSPACE_EXTENSION
from notebook.notebookapp import NotebookApp, aliases, flags
from notebook.utils import url_path_join as ujoin
from traitlets import Bool, Unicode

from ._version import __version__
from .extension import load_config, load_jupyter_server_extension
from .commands import (
    build, clean, get_app_dir, get_app_version, get_user_settings_dir,
    get_workspaces_dir
)


build_aliases = dict(base_aliases)
build_aliases['app-dir'] = 'LabBuildApp.app_dir'
build_aliases['name'] = 'LabBuildApp.name'
build_aliases['version'] = 'LabBuildApp.version'

build_flags = dict(flags)
build_flags['dev'] = (
    {'LabBuildApp': {'dev_build': True}},
    "Build in Development mode"
)

version = __version__
app_version = get_app_version()
if version != app_version:
    version = '%s (dev), %s (app)' % (__version__, app_version)


class LabBuildApp(JupyterApp):
    version = version
    description = """
    Build the JupyterLab application

    The application is built in the JupyterLab app directory in `/staging`.
    When the build is complete it is put in the JupyterLab app `/static`
    directory, where it is used to serve the application.
    """
    aliases = build_aliases
    flags = build_flags

    app_dir = Unicode('', config=True,
        help="The app directory to build in")

    name = Unicode('JupyterLab', config=True,
        help="The name of the built application")

    version = Unicode('', config=True,
        help="The version of the built application")

    dev_build = Bool(True, config=True,
        help="Whether to build in dev mode (defaults to dev mode)")

    def start(self):
        command = 'build:prod' if not self.dev_build else 'build'
        app_dir = self.app_dir or get_app_dir()
        self.log.info('JupyterLab %s', version)
        self.log.info('Building in %s', app_dir)
        build(app_dir=app_dir, name=self.name, version=self.version,
              command=command, logger=self.log)


clean_aliases = dict(base_aliases)
clean_aliases['app-dir'] = 'LabCleanApp.app_dir'


class LabCleanApp(JupyterApp):
    version = version
    description = """
    Clean the JupyterLab application

    This will clean the app directory by removing the `staging` and `static`
    directories.
    """
    aliases = clean_aliases

    app_dir = Unicode('', config=True, help='The app directory to clean')

    def start(self):
        clean(self.app_dir)


class LabPathApp(JupyterApp):
    version = version
    description = """
    Print the configured paths for the JupyterLab application

    The application path can be configured using the JUPYTERLAB_DIR
        environment variable.
    The user settings path can be configured using the JUPYTERLAB_SETTINGS_DIR
        environment variable or it will fall back to
        `/lab/user-settings` in the default Jupyter configuration directory.
    The workspaces path can be configured using the JUPYTERLAB_WORKSPACES_DIR
        environment variable or it will fall back to
        '/lab/workspaces' in the default Jupyter configuration directory.
    """

    def start(self):
        print('Application directory:   %s' % get_app_dir())
        print('User Settings directory: %s' % get_user_settings_dir())
        print('Workspaces directory: %s' % get_workspaces_dir())


class LabWorkspaceExportApp(JupyterApp):
    version = version
    description = """
    Export a JupyterLab workspace
    """

    def start(self):
        app = LabApp()
        base_url = app.base_url
        config = load_config(app)
        directory = config.workspaces_dir
        page_url = config.page_url

        if len(self.extra_args) > 1:
            print('Too many arguments were provided for workspace export.')
            sys.exit(1)

        raw = (page_url if not self.extra_args
               else ujoin(config.workspaces_url, self.extra_args[0]))
        slug = slugify(raw, base_url)
        workspace_path = os.path.join(directory, slug + WORKSPACE_EXTENSION)

        if os.path.exists(workspace_path):
            with open(workspace_path) as fid:
                try:  # to load the workspace file.
                    print(fid.read())
                except Exception as e:
                    print(json.dumps(dict(data=dict(), metadata=dict(id=raw))))
        else:
            print(json.dumps(dict(data=dict(), metadata=dict(id=raw))))


class LabWorkspaceImportApp(JupyterApp):
    version = version
    description = """
    Import a JupyterLab workspace
    """

    def start(self):
        app = LabApp()
        base_url = app.base_url
        config = load_config(app)
        directory = config.workspaces_dir
        page_url = config.page_url
        workspaces_url = config.workspaces_url

        if len(self.extra_args) != 1:
            print('One argument is required for workspace import.')
            sys.exit(1)

        file_name = self.extra_args[0]
        file_path = os.path.abspath(file_name)

        if not os.path.exists(file_path):
            print('%s does not exist.' % file_name)
            sys.exit(1)

        workspace = dict()
        with open(file_path) as fid:
            try:  # to load, parse, and validate the workspace file.
                workspace = self._validate(fid, page_url, workspaces_url)
            except Exception as e:
                print('%s is not a valid workspace:\n%s' % (file_name, e))
                sys.exit(1)

        if not os.path.exists(directory):
            try:
                os.makedirs(directory)
            except Exception as e:
                print('Workspaces directory could not be created:\n%s' % e)
                sys.exit(1)

        slug = slugify(workspace['metadata']['id'], base_url)
        workspace_path = os.path.join(directory, slug + WORKSPACE_EXTENSION)

        # Write the workspace data to a file.
        with open(workspace_path, 'w') as fid:
            fid.write(json.dumps(workspace))

        print('Saved workspace: %s' % workspace_path)

    def _validate(self, data, page_url, workspaces_url):
        workspace = json.load(data)

        if 'data' not in workspace:
            raise Exception('The `data` field is missing.')

        if 'metadata' not in workspace:
            raise Exception('The `metadata` field is missing.')

        if 'id' not in workspace['metadata']:
            raise Exception('The `id` field is missing in `metadata`.')

        id = workspace['metadata']['id']
        if id != page_url and not id.startswith(workspaces_url):
            error = '%s does not match page_url or start with workspaces_url.'
            raise Exception(error % id)

        return workspace


class LabWorkspaceApp(JupyterApp):
    version = version
    description = """
    Import or export a JupyterLab workspace
    """

    subcommands = dict()
    subcommands['export'] = (
        LabWorkspaceExportApp,
        LabWorkspaceExportApp.description.splitlines()[0]
    )
    subcommands['import'] = (
        LabWorkspaceImportApp,
        LabWorkspaceImportApp.description.splitlines()[0]
    )


lab_aliases = dict(aliases)
lab_aliases['app-dir'] = 'LabApp.app_dir'

lab_flags = dict(flags)
lab_flags['core-mode'] = (
    {'LabApp': {'core_mode': True}},
    "Start the app in core mode."
)
lab_flags['dev-mode'] = (
    {'LabApp': {'dev_mode': True}},
    "Start the app in dev mode for running from source."
)
lab_flags['watch'] = (
    {'LabApp': {'watch': True}},
    "Start the app in watch mode."
)


class LabApp(NotebookApp):
    version = version

    description = """
    JupyterLab - An extensible computational environment for Jupyter.

    This launches a Tornado based HTML Server that serves up an
    HTML5/Javascript JupyterLab client.

    JupyterLab has three different modes of running:

    * Core mode (`--core-mode`): in this mode JupyterLab will run using the JavaScript
      assets contained in the installed `jupyterlab` Python package. In core mode, no
      extensions are enabled. This is the default in a stable JupyterLab release if you
      have no extensions installed.
    * Dev mode (`--dev-mode`): uses the unpublished local JavaScript packages in the
      `dev_mode` folder.  In this case JupyterLab will show a red stripe at the top of
      the page.  It can only be used if JupyterLab is installed as `pip install -e .`.
    * App mode: JupyterLab allows multiple JupyterLab "applications" to be
      created by the user with different combinations of extensions. The `--app-dir` can
      be used to set a directory for different applications. The default application
      path can be found using `jupyter lab path`.
    """

    examples = """
        jupyter lab                       # start JupyterLab
        jupyter lab --dev-mode            # start JupyterLab in development mode, with no extensions
        jupyter lab --core-mode           # start JupyterLab in core mode, with no extensions
        jupyter lab --app-dir=~/myjupyterlabapp # start JupyterLab with a particular set of extensions
        jupyter lab --certfile=mycert.pem # use SSL/TLS certificate
    """

    aliases = lab_aliases
    flags = lab_flags

    subcommands = dict(
        build=(LabBuildApp, LabBuildApp.description.splitlines()[0]),
        clean=(LabCleanApp, LabCleanApp.description.splitlines()[0]),
        path=(LabPathApp, LabPathApp.description.splitlines()[0]),
        paths=(LabPathApp, LabPathApp.description.splitlines()[0]),
        workspace=(LabWorkspaceApp, LabWorkspaceApp.description.splitlines()[0]),
        workspaces=(LabWorkspaceApp, LabWorkspaceApp.description.splitlines()[0])
    )

    default_url = Unicode('/lab', config=True,
        help="The default URL to redirect to from `/`")

    app_dir = Unicode(get_app_dir(), config=True,
        help="The app directory to launch JupyterLab from.")

    user_settings_dir = Unicode(get_user_settings_dir(), config=True,
        help="The directory for user settings.")

    workspaces_dir = Unicode(get_workspaces_dir(), config=True,
        help="The directory for workspaces")

    core_mode = Bool(False, config=True,
        help="""Whether to start the app in core mode. In this mode, JupyterLab
        will run using the JavaScript assets that are within the installed
        JupyterLab Python package. In core mode, third party extensions are disabled.
        The `--dev-mode` flag is an alias to this to be used when the Python package
        itself is installed in development mode (`pip install -e .`).
        """)

    dev_mode = Bool(False, config=True,
        help="""Whether to start the app in dev mode. Uses the unpublished local
        JavaScript packages in the `dev_mode` folder.  In this case JupyterLab will
        show a red stripe at the top of the page.  It can only be used if JupyterLab
        is installed as `pip install -e .`.
        """)

    watch = Bool(False, config=True,
        help="Whether to serve the app in watch mode")

    def init_webapp(self, *args, **kwargs):
        super().init_webapp(*args, **kwargs)
        settings = self.web_app.settings
        if 'page_config_data' not in settings:
            settings['page_config_data'] = {}

        # Handle quit button with support for Notebook < 5.6
        settings['page_config_data']['quit_button'] = getattr(self, 'quit_button', False)

    def init_server_extensions(self):
        """Load any extensions specified by config.

        Import the module, then call the load_jupyter_server_extension function,
        if one exists.

        If the JupyterLab server extension is not enabled, it will
        be manually loaded with a warning.

        The extension API is experimental, and may change in future releases.
        """
        super(LabApp, self).init_server_extensions()
        msg = 'JupyterLab server extension not enabled, manually loading...'
        if not self.nbserver_extensions.get('jupyterlab', False):
            self.log.warn(msg)
            load_jupyter_server_extension(self)


#-----------------------------------------------------------------------------
# Main entry point
#-----------------------------------------------------------------------------

main = launch_new_instance = LabApp.launch_instance

if __name__ == '__main__':
    main()
