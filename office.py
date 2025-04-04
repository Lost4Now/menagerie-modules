# -*- coding: utf-8 -*-
# This file is part of menagerie - https://github.com/menagerie-framework/menagerie
# See the file "LICENSE" for copying permission.

"""
Code based on the python-oletools package by Philippe Lagadec 2012-10-18
http://www.decalage.info/python/oletools
"""

import os
import struct
import zipfile
import xml.etree.ElementTree as ET

from menagerie.common.utils import string_clean, string_clean_hex
from menagerie.common.abstracts import Module
from menagerie.core.session import __sessions__

from io import BytesIO, open

try:
    import olefile
    from oletools import msodde
    from oletools import ooxml

    from oletools.olevba import VBA_Parser, VBA_Scanner
    HAVE_OLE = True
except ImportError:
    HAVE_OLE = False

try:
    from oletools import pyxswf
    HAVE_PYXSWF = True
except ImportError:
    HAVE_PYXSWF = False


class Office(Module):
    cmd = "office"
    description = "Office Document Parser"
    authors = ["Kevin Breen", "nex"]
    categories = ["document"]

    def __init__(self):
        super(Office, self).__init__()
        self.parser.add_argument("-m", "--meta", action="store_true", help="Get the metadata")
        self.parser.add_argument("-o", "--oleid", action="store_true", help="Get the OLE information")
        self.parser.add_argument("-s", "--streams", action="store_true", help="Show the document streams")
        self.parser.add_argument("-e", "--export", metavar="dump_path", help="Export all objects")
        self.parser.add_argument("-v", "--vba", action="store_true", help="Analyse Macro Code")
        self.parser.add_argument("-c", "--code", metavar="code_path", help="Export Macro Code to File")
        self.parser.add_argument("-d", "--dde", action="store_true", help="Get DDE Links")

    #==========================================================================
    # Helper functions.
    #==========================================================================

    def print_swf_header_info(self, header):
        if header is None:
            self.log("warning", "Error could not read header")
            return
        self.log("item", "File Header: {}".format(header["signature"].decode()))
        if header["compression"] is not None:
            self.log("item", "Compression Type: {}".format(header["compression"]))
        if header["compression"] == "lzma":
            self.log("item", "Compressed Data Length: {}".format(header["compressed_len"]))
        self.log("item", "File Veader: {}".format(header["version"]))
        self.log("item", "File Size: {}".format(header["file_length"]))
        self.log("item", "Rect Nbit: {}".format(header["nbits"]))
        self.log("item", "Rect Xmin: {}".format(header["xmin"]))
        self.log("item", "Rect Xmax: {}".format(header["xmax"]))
        self.log("item", "Rect Ymin: {}".format(header["ymin"]))
        self.log("item", "Rect Ymax: {}".format(header["ymax"]))
        self.log("item", "Frame Rate: {}".format(header["frame_rate"]))
        self.log("item", "Frace Count: {}".format(header["frame_count"]))

    def detect_flash(self, section):
        if not HAVE_PYXSWF:
            self.log("warning", "Unable to search for Flash objects, requires xxxswf")
            return []

        section = BytesIO(section)
        swf_data = pyxswf.xxxswf.findSWF(section)
        if len(swf_data) == 0:
            return []

        full_content = section.getvalue()
        to_return = []
        for index, start in enumerate(swf_data):
            swf = pyxswf.xxxswf.verifySWF(full_content[start:], 0)
            if swf:
                headers = pyxswf.xxxswf.headerInfo(swf)
                to_return.append((headers.header, swf))

        return to_return

    #==========================================================================
    # OLE functions
    #==========================================================================

    def ole_meta(self, ole):
        """
        Get metadata on the Office document.
        """
        meta = ole.get_metadata()
        for attribs in ["SUMMARY_ATTRIBS", "DOCSUM_ATTRIBS"]:
            self.log("info", "{0} Metadata".format(string_clean(attribs)))
            rows = []
            for key in getattr(meta, attribs):
                rows.append([key, string_clean(getattr(meta, key))])

            self.log("table", dict(header=["Name", "Value"], rows=rows))

        ole.close()

    def ole_structure(self, ole):
        """
        """
        rows = []
        rows.append([
            1,
            "Root",
            "",
            ole.root.getctime() if ole.root.getctime() else "",
            ole.root.getmtime() if ole.root.getmtime() else ""
        ])

        counter = 2
        for obj in ole.listdir(streams=True, storages=True):
            has_macro = ""
            try:
                if "\x00Attribu" in ole.openstream(obj).read():
                    has_macro = "Yes"
            except Exception:
                pass

            rows.append([
                counter,
                string_clean("/".join(obj)),
                has_macro,
                ole.getctime(obj) if ole.getctime(obj) else "",
                ole.getmtime(obj) if ole.getmtime(obj) else ""
            ])

            counter += 1

        self.log("info", "OLE Structure:")
        self.log("table", dict(header=["#", "Object", "Macro", "Creation", "Modified"], rows=rows))

        ole.close()

    def _safe_makedir(self, path):
        if not os.path.exists(path):
            try:
                os.makedirs(path)
            except Exception as e:
                self.log("error", "Unable to create directory at {0}: {1}".format(path, e))
                return False
        else:
            if not os.path.isdir(path):
                self.log("error", "You need to specify a folder, not a file")
                return False

        return True

    def ole_export(self, ole, export_path):
        if not self._safe_makedir(export_path):
            return

        for stream in ole.listdir(streams=True, storages=True):
            try:
                stream_content = ole.openstream(stream).read()
            except Exception as e:
                self.log("warning", "Unable to open stream {0}: {1}".format(string_clean("/".join(stream)), e))
                continue

            store_path = os.path.join(export_path, string_clean("-".join(stream)))

            flash_objects = self.detect_flash(ole.openstream(stream).read())
            if len(flash_objects) > 0:
                self.log("info", "Saving Flash objects...")
                count = 1

                for header, flash_object in flash_objects:
                    self.print_swf_header_info(header)
                    save_path = "{0}-FLASH-Decompressed{1}".format(store_path, count)
                    with open(save_path, "wb") as flash_out:
                        flash_out.write(flash_object)

                    self.log("item", "Saved Decompressed Flash File to {0}".format(save_path))
                    count += 1

            with open(store_path, "wb") as out:
                out.write(stream_content)

            self.log("info", "Saved stream to {0}".format(store_path))

        ole.close()

    def ole_id(self, ole):
        has_summary = False
        is_encrypted = False
        is_word = False
        is_excel = False
        is_ppt = False
        is_visio = False
        has_macros = False
        has_flash = 0

        # SummaryInfo.
        if ole.exists("\x05SummaryInformation"):
            suminfo = ole.getproperties("\x05SummaryInformation")
            has_summary = True
            # Encryption check.
            if 0x13 in suminfo:
                if suminfo[0x13] & 1:
                    is_encrypted = True

        # Word Check.
        if ole.exists("WordDocument"):
            is_word = True
            s = ole.openstream(["WordDocument"])
            s.read(10)
            temp16 = struct.unpack("H", s.read(2))[0]

            if (temp16 & 0x0100) >> 8:
                is_encrypted = True

        # Excel Check.
        if ole.exists("Workbook") or ole.exists("Book"):
            is_excel = True

        # Macro Check.
        if ole.exists("Macros"):
            has_macros = True

        for obj in ole.listdir(streams=True, storages=True):
            if "VBA" in obj:
                has_macros = True

        # PPT Check.
        if ole.exists("PowerPoint Document"):
            is_ppt = True

        # Visio check.
        if ole.exists("VisioDocument"):
            is_visio = True

        # Flash Check.
        for stream in ole.listdir():
            has_flash += len(self.detect_flash(ole.openstream(stream).read()))

        # Put it all together.
        rows = [
            ["Summary Information", has_summary],
            ["Word", is_word],
            ["Excel", is_excel],
            ["PowerPoint", is_ppt],
            ["Visio", is_visio],
            ["Encrypted", is_encrypted],
            ["Macros", has_macros],
            ["Flash Objects", has_flash]
        ]

        # Print the results.
        self.log("info", "OLE Info:")
        # TODO: There are some non ascii chars that need stripping.
        self.log("table", dict(header=["Test", "Result"], rows=rows))

        ole.close()

    ##
    # XML FUNCTIONS
    #

    def _xml_string_meta(self, xml_string):
        doc_meta = []
        xml_root = ET.fromstring(xml_string)
        for child in xml_root:
            doc_meta.append([child.tag.split("}")[1], child.text])

        return doc_meta

    def xml_meta(self, zip_xml):
        media_list = []
        embedded_list = []
        vba_list = []
        activex_list = []
        for name in zip_xml.namelist():
            if name == "docProps/app.xml":
                meta1 = self._xml_string_meta(zip_xml.read(name))
            if name == "docProps/core.xml":
                meta2 = self._xml_string_meta(zip_xml.read(name))
            if name.startswith("word/media/"):
                media_list.append(name.split("/")[-1])
            # if name is vba, need to add multiple macros
            if name.startswith("word/embeddings"):
                embedded_list.append(name.split("/")[-1])
            if name == "word/vbaProject.bin":
                vba_list.append(name.split("/")[-1])
            if name.startswith("word/activeX/"):
                activex_list.append(name.split("/")[-1])

        # Print the results.
        self.log("info", "App MetaData:")
        self.log("table", dict(header=["Field", "Value"], rows=meta1))
        self.log("info", "Core MetaData:")
        self.log("table", dict(header=["Field", "Value"], rows=meta2))
        if len(embedded_list) > 0:
            self.log("info", "Embedded Objects")
            for item in embedded_list:
                self.log("item", item)
        if len(vba_list) > 0:
            self.log("info", "Macro Objects")
            for item in vba_list:
                self.log("item", item)
        if len(activex_list) > 0:
            self.log("info", "ActiveX Objects")
            for item in activex_list:
                self.log("item", item)
        if len(media_list) > 0:
            self.log("info", "Media Objects")
            for item in media_list:
                self.log("item", item)

    def xml_structure(self, zip_xml):
        self.log("info", "Document Structure")
        for name in zip_xml.namelist():
            self.log("item", name)

    def xml_export(self, zip_xml, export_path):
        if not os.path.exists(export_path):
            try:
                os.makedirs(export_path)
            except Exception as e:
                self.log("error", "Unable to create directory at {0}: {1}".format(export_path, e))
                return
        else:
            if not os.path.isdir(export_path):
                self.log("error", "You need to specify a folder, not a file")
                return
        try:
            zip_xml.extractall(export_path)
            self.log("info", "Saved all objects to {0}".format(export_path))
        except Exception as e:
            self.log("error", "Unable to export objects: {0}".format(e))

    #==========================================================================
    # Macros
    #==========================================================================

    def parse_vba(self, save_path):
        """
        Parse VBA scripts.
        """
        save = False
        vbaparser = VBA_Parser(__sessions__.current.file.path)
        # Check for Macros
        if not vbaparser.detect_vba_macros():
            self.log("error", "No macros detected")
            return
        self.log("info", "Macros detected")
        # try:
        if True:
            an_results = {"AutoExec": [], "Suspicious": [], "IOC": [], "Hex String": [], "Base64 String": [], "Dridex string": [], "VBA string": []}
            for (filename, stream_path, vba_filename, vba_code) in vbaparser.extract_macros():
                self.log("info", "Stream Details")
                self.log("item", "OLE Stream: {0}".format(string_clean(stream_path)))
                self.log("item", "VBA Filename: {0}".format(string_clean(vba_filename)))
                # Analyse the VBA Code
                vba_scanner = VBA_Scanner(vba_code)
                analysis = vba_scanner.scan(include_decoded_strings=True)
                for kw_type, keyword, description in analysis:
                    an_results[kw_type].append([string_clean_hex(keyword), description])

                # Save the code to external File
                if save_path:
                    try:
                        with open(save_path, "a") as out:
                            out.write(vba_code)
                        save = True
                    except Exception as e:
                        self.log("error", "Unable to write to {0}: {1}".format(save_path, e))
                        return

            # Print all tables together
            if an_results["AutoExec"]:
                self.log("info", "Autorun macros found")
                self.log("table", dict(header=["Method", "Description"], rows=an_results["AutoExec"]))

            if an_results["Suspicious"]:
                self.log("info", "Suspicious keywords found")
                self.log("table", dict(header=["Keyword", "Description"], rows=an_results["Suspicious"]))

            if an_results["IOC"]:
                self.log("info", "Possible IOCs")
                self.log("table", dict(header=["IOC", "Type"], rows=an_results["IOC"]))

            if an_results["Hex String"]:
                self.log("info", "Hex strings")
                self.log("table", dict(header=["Decoded", "Raw"], rows=an_results["Hex String"]))

            if an_results["Base64 String"]:
                self.log("info", "Base64 strings")
                self.log("table", dict(header=["Decoded", "Raw"], rows=an_results["Base64 String"]))

            if an_results["Dridex string"]:
                self.log("info", "Dridex strings")
                self.log("table", dict(header=["Decoded", "Raw"], rows=an_results["Dridex string"]))

            if an_results["VBA string"]:
                self.log("info", "VBA strings")
                self.log("table", dict(header=["Decoded", "Raw"], rows=an_results["VBA string"]))

            if save:
                self.log("success", "Writing VBA Code to {0}".format(save_path))

        # Close the file
        vbaparser.close()

    #==========================================================================
    # DDE
    #==========================================================================

    def get_dde(self, file_path):
        """
        Find DDE links.
        """
        try:
            dde_result = msodde.process_file(file_path, "only dde")
            dde_fields = [[i + 1, x.strip()] for i, x in enumerate(dde_result.split("\n"))]
            if (len(dde_fields) == 1) and (dde_fields[0][1] == ""):
                self.log("info", "No DDE links detected.")
            else:
                self.log("success", "DDE links detected.")
                header = ["#", "DDE"]
                self.log("table", dict(header=header, rows=dde_fields))
        except Exception:
            self.log("error", "Unable to process file")

    #==========================================================================
    # Main
    #==========================================================================

    def run(self):
        """
        Main function.
        """
        super(Office, self).run()
        if self.args is None:
            return

        if not __sessions__.is_set():
            self.log("error", "No open session. This command expects a file to be open.")
            return

        if not HAVE_OLE:
            self.log("error", "Missing dependency, install OleFileIO (`pip install olefile oletools`)")
            return

        file_data = __sessions__.current.file.data
        if file_data.startswith(b"<?xml"):
            OLD_XML = file_data
        else:
            OLD_XML = False

        if file_data.startswith(b"MIME-Version:") and "application/x-mso" in file_data:
            MHT_FILE = file_data
        else:
            MHT_FILE = False

        # Check for old office formats
        try:
            doctype = ooxml.get_type(__sessions__.current.file.path)
            OOXML_FILE = True
        except Exception:
            OOXML_FILE = False

        # set defaults
        XLSX_FILE = False
        EXCEL_XML_FILE = False
        DOCX_FILE = False
        if OOXML_FILE is True:
            if doctype == ooxml.DOCTYPE_EXCEL:
                XLSX_FILE = True
            elif doctype in (ooxml.DOCTYPE_EXCEL_XML, ooxml.DOCTYPE_EXCEL_XML2003):
                EXCEL_XML_FILE = True
            elif doctype in (ooxml.DOCTYPE_WORD_XML, ooxml.DOCTYPE_WORD_XML2003):
                DOCX_FILE = True

        # Tests to check for valid Office structures.
        OLE_FILE = olefile.isOleFile(__sessions__.current.file.path)
        XML_FILE = zipfile.is_zipfile(__sessions__.current.file.path)
        if OLE_FILE:
            ole = olefile.OleFileIO(__sessions__.current.file.path)
        elif XML_FILE:
            zip_xml = zipfile.ZipFile(__sessions__.current.file.path, "r")
        elif OLD_XML:
            pass
        elif MHT_FILE:
            pass
        elif DOCX_FILE:
            pass
        elif EXCEL_XML_FILE:
            pass
        elif XLSX_FILE:
            pass
        else:
            self.log("error", "Not a valid office document")
            return

        if self.args.export is not None:
            if OLE_FILE:
                self.ole_export(ole, self.args.export)
            elif XML_FILE:
                self.xml_export(zip_xml, self.args.export)
        elif self.args.meta:
            if OLE_FILE:
                self.ole_meta(ole)
            elif XML_FILE:
                self.xml_meta(zip_xml)
        elif self.args.streams:
            if OLE_FILE:
                self.ole_structure(ole)
            elif XML_FILE:
                self.xml_structure(zip_xml)
        elif self.args.oleid:
            if OLE_FILE:
                self.ole_id(ole)
            else:
                self.log("error", "Not an OLE file")
        elif self.args.vba or self.args.code:
            self.parse_vba(self.args.code)
        elif self.args.dde:
            self.get_dde(__sessions__.current.file.path)
        else:
            self.log("error", "At least one of the parameters is required")
            self.usage()
