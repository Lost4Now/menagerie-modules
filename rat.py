# -*- coding: utf-8 -*-
# This file is part of menagerie - https://github.com/menagerie-framework/menagerie
# See the file 'LICENSE' for copying permission.

import os
import importlib

import menagerie
from menagerie.common.out import bold
from menagerie.common.abstracts import Module
from menagerie.core.session import __sessions__

try:
    from scandir import walk
except ImportError:
    from os import walk

try:
    import yara
    HAVE_YARA = True
except ImportError:
    HAVE_YARA = False


class RAT(Module):
    cmd = 'rat'
    description = 'Extract information from known RAT families'
    authors = ['Kevin Breen', 'nex']

    def __init__(self):
        super(RAT, self).__init__()
        group = self.parser.add_mutually_exclusive_group(required=True)
        group.add_argument('-a', '--auto', action='store_true', help='Automatically detect RAT')
        group.add_argument('-f', '--family', help='Specify which RAT family')
        group.add_argument('-l', '--list', action='store_true', help='List available RAT modules')

    def list(self):
        self.log('info', "List of available RAT modules:")

        rat_modules_path = os.path.join(os.path.join(os.path.dirname(menagerie.__file__), 'modules/rats/'))
        for folder, folders, files in walk(rat_modules_path):
            for file_name in files:
                if not file_name.endswith('.py') or file_name.startswith('__init__'):
                    continue

                self.log('item', os.path.join(folder, file_name))

    def get_config(self, family):
        if not __sessions__.is_set():
            self.log('error', "No open session. This command expects a file to be open.")
            return

        try:
            module = importlib.import_module('menagerie.modules.rats.{0}'.format(family))
        except ImportError:
            self.log('error', "There is no module for family {0}".format(bold(family)))
            return

        try:
            config = module.config(__sessions__.current.file.data)
        except Exception:
            config = None
        if not config:
            self.log('error', "No Configuration Detected")
            return

        rows = []
        for key, value in config.items():
            rows.append([key, value])

        rows = sorted(rows, key=lambda entry: entry[0])

        self.log('info', "Configuration:")
        self.log('table', dict(header=['Key', 'Value'], rows=rows))

    def auto(self):
        if not HAVE_YARA:
            self.log('error', "Missing dependency, install yara (see http://plusvic.github.io/yara/)")
            return

        if not __sessions__.is_set():
            self.log('error', "No open session. This command expects a file to be open.")
            return

        rules = yara.compile(os.path.join(os.path.dirname(menagerie.__file__), "data", "yara", "rats.yara"))
        for match in rules.match(__sessions__.current.file.path):
            if 'family' in match.meta:
                self.log('info', "Automatically detected supported RAT {0}".format(match.rule))
                self.get_config(match.meta['family'])
                return

        self.log('info', "No known RAT detected")

    def run(self):
        super(RAT, self).run()

        if self.args is None:
            return

        if self.args.auto:
            self.auto()
        elif self.args.family:
            self.get_config(self.args.family)
        elif self.args.list:
            self.list()
