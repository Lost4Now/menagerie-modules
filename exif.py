# -*- coding: utf-8 -*-
# This file is part of menagerie - https://github.com/menagerie-framework/menagerie
# See the file 'LICENSE' for copying permission.


from menagerie.common.abstracts import Module
from menagerie.core.session import __sessions__

try:
    import exiftool
    HAVE_EXIF = True
except ImportError:
    HAVE_EXIF = False


class Exif(Module):
    cmd = 'exif'
    description = 'Extract Exif MetaData'
    authors = ['Kevin Breen']

    def __init__(self):
        super(Exif, self).__init__()

    def run(self):
        super(Exif, self).run()
        if self.args is None:
            return

        if not __sessions__.is_set():
            self.log('error', "No open session. This command expects a file to be open.")
            return

        if not HAVE_EXIF:
            self.log('error', "Missing dependency, install pyexiftool")
            return

        try:
            with exiftool.ExifTool() as et:
                metadata = et.get_metadata(__sessions__.current.file.path)
        except OSError:
            self.log('error', "Exiftool is not installed")
            return

        rows = []
        for key, value in metadata.items():
            rows.append([key, value])

        rows = sorted(rows, key=lambda entry: entry[0])

        self.log('info', "MetaData:")
        self.log('table', dict(header=['Key', 'Value'], rows=rows))
