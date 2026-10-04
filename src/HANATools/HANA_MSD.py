import hashlib
import struct
import copy
import os
from typing import BinaryIO

class MsdCipher:
    def __init__(self, key, block_size: int = 0x20, encoding="utf8"):
        self.key = key
        self.block_size = block_size
        self.encoding = encoding

    ## 加密与解密的操作一致
    def decrypt(self, data):
        output = bytearray()
        data_len = len(data)
        offset = 0
        block_num = 0

        while offset + self.block_size <= data_len:
            chunk = data[offset : offset + self.block_size]
            self._process_chunk(chunk, output, block_num)
            offset += self.block_size
            block_num += 1

        if offset < data_len:
            remaining_chunk = data[offset:]
            self._process_chunk(remaining_chunk, output, block_num)

        return bytes(output)

    def _process_chunk(self, chunk: bytes, output: bytearray, block_num: int):
        chunk_key = f"{self.key}{block_num}".encode(self.encoding)
        md5_hash = hashlib.md5(chunk_key).hexdigest()
        for j in range(len(chunk)):
            output.append(chunk[j] ^ ord(md5_hash[j % 32])) 


## 未完善
## 尝试从MSD读取部分脚本信息(如语音、文本、背景、立绘等)
class MsdReader:
    def __init__(self, stream: str | os.PathLike[str] | BinaryIO, encoding):
        if isinstance(stream, (str, os.PathLike)):
            self.stream = open(stream, "rb")
            self._own_stream = True
        else:
            self.stream = stream
            self._own_stream = False
        if not self._is_msd_file():
            raise ValueError("the file is not MSD file")
        self.encoding = encoding
        self.size = self.get_size()
    
    ## MSD读取轻量版（仅含对话、语音、背景、立绘、音效、背景音乐）
    def msd_read_light(self):
        stream = self.stream
        offset = 0
        file_size = self.size
            
        ## 跳过头部数据区域
        stream.seek(0x14)
        int01 = struct.unpack("<i", stream.read(4))[0]
        int02 = struct.unpack("<i", stream.read(4))[0]
        offset = 0x0458 + 4 * (int01 + int02)
        stream.seek(offset)

        ## 读取指令数据
        codes = []
        while offset + 4 <= file_size:
            ## 读取指令及参数区域大小
            code_raw = stream.read(2)
            size = struct.unpack("<h", stream.read(2))[0]
            offset += 4

            if code_raw in self.codes_list_light:
                code = self.codes_list_light[code_raw]

                ## 读取部分已知指令及其参数
                args_data = stream.read(size)
                offset  += size
                args = self.args_read(args_data)
                codes.append({"code":code, "args":args})
            else:
                offset += size
                stream.seek(offset)

        return  copy.deepcopy(codes)

    ## MSD读取，指令部分保留原始字节；从0x0458开始的数据以4个字节为单元，保留每个单元的前两个字节
    def msd_read(self):
        stream = self.stream
        offset = 0
        file_size = self.size

        ## 文件头部数据
        stream.seek(0)
        file_signature  = stream.read(0x10)
        bytes01         = stream.read(4)
        int01           = struct.unpack("<i", stream.read(4))[0]
        int02           = struct.unpack("<i", stream.read(4))[0]

        ## 读取从0x0458开始的数据，以4个字节为单元，总单元数目为int01与int02之和
        stream.seek(0x0458)
        head_codes = []
        for _ in range(int01 + int02):
            data = stream.read(4)
            code = data[0:2]
            head_codes.append(bytes(code))

        ## 读取指令数据
        offset = stream.tell()
        codes = []
        while offset + 4 <= file_size:
            code = stream.read(2)
            args_size = struct.unpack("<h", stream.read(2))[0]
            offset += 4

            args_bytes = stream.read(args_size)
            offset += args_size
            args = self.args_read(args_bytes)
            codes.append({"code":bytes(code), "args":args})

        ## 暂不处理剩余字节
        #if offset < file_size:
        #    remaining_bytes = stream.read()

        msd_data = {"file_signature": file_signature, "bytes01": bytes01, "int01": int01, "int02": int02, "head_codes": head_codes, "codes": codes}
        return copy.deepcopy(msd_data)

    ## MSD读取，但只读取对话相关语句，用于语音文件标注
    def msd_read_voice_annotation(self):
        stream = self.stream
        offset = 0
        file_size = self.size
            
        stream.seek(0x14)
        int01 = struct.unpack("<i", stream.read(4))[0]
        int02 = struct.unpack("<i", stream.read(4))[0]
        offset = 0x0458 + 4 * (int01 + int02)
        stream.seek(offset)

        codes = []
        while offset + 4 <= file_size:
            code_raw = stream.read(2)
            size = struct.unpack("<h", stream.read(2))[0]
            offset += 4

            if code_raw in (b"\xd7\x07", b"\xd8\x07", b"\xda\x07"):
                code = self.codes_list_light[code_raw]
                args_data = stream.read(size)
                offset  += size
                args = self.args_read(args_data)
                codes.append({"code":code, "args":args})
            else:
                offset += size
                stream.seek(offset)

        return  copy.deepcopy(codes)

    def args_read(self, data):
        data_size = len(data)
        offset = 0
        args = []
        while offset < data_size:
            flag = data[offset]
            offset += 1
            ## `01 `为4字节整数标志
            if flag == 1:
                arg_data = data[offset:offset+4]
                offset += 4
                arg = struct.unpack("<i", arg_data)[0]
                args.append({"flag": flag, "value": arg})
            ## `02 `标志也是4字节数据，具体意义不明，暂当4字节整数处理
            elif flag == 2:
                arg_data = data[offset:offset+4]
                offset += 4
                arg = struct.unpack("<i", arg_data)[0]
                args.append({"flag": flag, "value": arg})
            ## `03 `为字符串标志，其后为字符串数据，直至字符串结束标志`00 `
            elif flag == 3:
                strbytes = bytearray()
                while  offset < data_size:
                    strbyte = data[offset]
                    offset += 1
                    if strbyte == b"\x00":
                        break
                    else:
                        strbytes += strbyte
                args.append({"flag": flag, "value": strbytes.decode(self.encoding)})
            ## `04 `曾出现在选项跳转相关指令`05 00 `的参数列表里，大小皆为0x20字节，具体意义不明，暂保留字节串
            elif flag == 4:
                arg_data = data[offset:offset + 0x20]
                offset += 0x20
                arg = arg_data
                args.append({"flag": flag, "value": arg})
            else:
                raise ValueError(f"unknown flag {flag}")
                #pass
            
        return args

    def get_size(self):
        current_offset = self.stream.tell()
        self.stream.seek(0, 2)
        size = self.stream.tell()
        self.stream.seek(current_offset)

        return size

    def _is_msd_file(self) -> bool:
        self.stream.seek(0)
        file_signature = self.stream.read(0x10)
        return file_signature == b"MSCENARIO FILE  "



    codes_list_light = {
        b"\xd7\x07" :   "char"  ,
        b"\xd8\x07" :   "voice" ,
        b"\xda\x07" :   "text"  ,
        b"\xed\x03" :   "title" ,
        b"\xc9\x00" :   "bgm"   ,
        b"\xd3\x00" :   "se"    ,
        b"\x64\x00" :   "image" ,
        b"\x65\x00" :   "image_clear"   ,
        b"\x66\x00" :   "image2" ,
        b"\x67\x00" :   "image_show"    ,
        b"\x6e\x00" :   "transfrom"     ,
        b"\xde\x07" :   "select"        ,   #???
        b"\x05\x00" :   "label"         ,   #???
    }

def is_msd_file(file_path) -> bool:
    with open(file_path, "rb") as file:
        file_signature = file.read(0x10)
    return file_signature == b"MSCENARIO FILE  "
