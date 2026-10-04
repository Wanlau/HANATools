import struct
import os
from typing import BinaryIO

from .HANA_MSD import MsdCipher

class FjsysExtracter:
    def __init__(self, stream: str | os.PathLike[str] | BinaryIO):
        if isinstance(stream, (str, os.PathLike)):
            self.stream = open(stream, "rb")
            self._own_stream = True
        else:
            self.stream = stream
            self._own_stream = False
        if not self._is_fjsys_file():
            raise ValueError("the file is not FJSYS file")
        self.header_read()
        self.entries_idx = None
        self.entries_name = None

    def header_read(self):
        stream = self.stream
        stream.seek(0)

        self.file_signature     = stream.read(8)
        self.first_entry_offset = struct.unpack("<I", stream.read(4))[0]
        self.names_size         = struct.unpack("<I", stream.read(4))[0]
        self.file_count         = struct.unpack("<I", stream.read(4))[0]

    def entries_idx_read(self):
        stream = self.stream
        stream.seek(0x54)

        entries_idx = []
        for _ in range(self.file_count):
            name_offset = struct.unpack("<I", stream.read(4))[0]
            size        = struct.unpack("<I", stream.read(4))[0]
            offset      = struct.unpack("<Q", stream.read(8))[0]
            entries_idx.append({"name_offset":name_offset, "size":size, "offset":offset})

        self.entries_idx = entries_idx

    def entries_name_read(self, encoding="utf8"):
        if self.entries_idx is None:
            self.entries_idx_read()

        stream = self.stream
        names_begin_offset = 0x54 + self.file_count * 0x10
        names_end_offset = names_begin_offset + self.names_size

        entries_name = []
        for idx in self.entries_idx:
            strbytes = bytearray()
            offset = names_begin_offset + idx["name_offset"]
            stream.seek(offset)
            while offset < names_end_offset:
                strbyte = stream.read(1)
                offset += 1
                if strbyte == b"\x00":
                    break
                else:
                    strbytes += strbyte
            entries_name.append(strbytes.decode(encoding))

        self.entries_name = entries_name

    def entries_extract(self, opt_dir, encoding="utf8", mgd_convert = False, msd_decrypt = False, msd_password = None, msd_password_encoding = None):
        if self.entries_name is None:
            self.entries_name_read()
        if not os.path.exists(opt_dir):
            os.makedirs(opt_dir)
        if msd_decrypt:
            if msd_password is None:
                msd_password = ""
            if msd_password_encoding is None:
                msd_password_encoding = encoding

        stream = self.stream
        for i, idx in enumerate(self.entries_idx):
            name = self.entries_name[i]
            offset = idx["offset"]
            size = idx["size"]

            stream.seek(offset)
            data = stream.read(size)
            if name.endswith((".msd", ".MSD")):
                if msd_decrypt:
                    cipher = MsdCipher(msd_password, encoding=msd_password_encoding)
                    data = cipher.decrypt(data)
            elif name.endswith((".mgd", ".MGD")):
                if mgd_convert:
                    pass

            with open(os.path.join(opt_dir, name), "wb") as file:
                file.write(data)

    def _is_fjsys_file(self) -> bool:
        self.stream.seek(0)
        file_signature = self.stream.read(8)
        return file_signature == b"FJSYS\x00\x00\x00"

class FjsysBuilder:
    pass



def is_fjsys_file(file_path) -> bool:
    with open(file_path, "rb") as file:
        file_signature = file.read(8)
    return file_signature == b"FJSYS\x00\x00\x00"
