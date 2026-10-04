import struct
import os
from typing import BinaryIO
from io import BytesIO

from PIL import Image
import numpy as np

class MgdConverter:
    def __init__(self, stream: str | os.PathLike[str] | BinaryIO):
        if isinstance(stream, (str, os.PathLike)):
            self.stream = open(stream, "rb")
            self._own_stream = True
        else:
            self.stream = stream
            self._own_stream = False
        if not self._is_mgd_file():
            raise ValueError("the file is not MGD file")
        self.header_read()
        self._body_size_check()

    ## 未完善，部分字段含义尚未弄清
    def header_read(self):
        stream = self.stream
        stream.seek(0)

        self.file_signature = stream.read(4)
        self.header_size    = struct.unpack("<h", stream.read(2))[0]

        stream.seek(0x0C)
        self.width          = struct.unpack("<h", stream.read(2))[0]
        self.height         = struct.unpack("<h", stream.read(2))[0]
        self.image_bmp_size = struct.unpack("<i", stream.read(4))[0]
        self.body_size      = struct.unpack("<i", stream.read(4))[0]
        self.mode           = struct.unpack("<h", stream.read(2))[0]

    def mgd_convert(self) -> Image:
        if self.mode == 0:
            img = self.mgd_convert_mode0()
        elif self.mode == 1:
            img = self.mgd_convert_mode1()
        elif self.mode == 2:
            img = self.mgd_convert_mode2()
        else:
            raise ValueError(f"unknown mgd mode: {self.mode:02d}")

        return img

    def mgd_convert_mode0(self):
        stream = self.stream
        stream.seek(self.header_size)

        data_size = struct.unpack("<i", stream.read(4))[0]
        data = stream.read(data_size)

        ## Pillow >= 9.4
        if any(data[3::4]):
            img = Image.frombytes("RGBA", (self.width, self.height), data, "raw", "BGRA")
        else:
            img = Image.frombytes("RGB", (self.width, self.height), data, "raw", "BGRX")
        
        return img

    ## 文件主体部分区域，开头的4字节数据为文件大小，其后为文件本身的数据。文件本身的数据又可被细分为两部分，即透明度通道部分和色彩通道部分。
    ## 透明度通道部分开头的4字节数据为透明度通道部分数据区域大小，其后即透明度通道部分的具体数据；透明度通道部分之后是色彩通道部分，开头的4字节数据为色彩通道部分数据区域大小，其后即色彩通道部分的数据。
    ## 透明度通道部分处理如下，先以含符号的整数格式读2字节数据作为计数，根据计数的正负可分为两种模式，即RLE压缩模式以及原始数据模式。若计数为正，则为原始数据模式，于其后读取[计数]个字节的数据作为[计数]个Alpha值；若计数为负，则为RLE压缩模式，取低15位并+1到实际重复次数，于其后读取1字节数据作为Alpha值，并重复填充相应的次数。
    ## 色彩通道部分处理如下，读1字节数据作为控制代码，其高2位作为控制标志，低6位作为计数，根据控制标志可分为三种模式，即增量编码模式、重复像素模式以及原始数据模式。若控制标志为0x80，则为增量编码模式，于其后读取2字节数据作为增量数据，结合上一个像素的BGR值确定新像素的BGR值，重复执行相应次数的计算填充操作；若控制标志0x40，则为重复像素模式，于其后读取3字节数据作为新像素的BGR值，并重复填充相应的次数；若控制标志为0x00，则为原始数据模式，于后读取3字节数据作为新像素的BGR值，重复执行相应次数的读取填充操作。增量编码模式的2字节增量数据，最高位为增量类型，其后依次是R、G、B的增量数据各5位。若最高位为1，则为无符号模式，各通道增量数据的5位数据视为增量值；若最高位为0，则为有符号模式，各通道增量数据的5位数据中的最高位为符号位，0为正，1为负，后4位数据视为增量值。
    ## 补充，模式0和模式1中，若透明度通道部分的数据都是`00`，则此图像无有效透明度数据，此时应视为RGB图像(或者说透明度皆视为`FF`)。
    def mgd_convert_mode1(self):
        stream = self.stream
        stream.seek(self.header_size)

        data_size = struct.unpack("<i", stream.read(4))[0]
        image_data = np.zeros((self.height, self.width, 4), dtype=np.uint8)

        alpha_size = struct.unpack("<i", stream.read(4))[0]
        stream.seek(self.header_size + alpha_size + 8)
        color_size = struct.unpack("<i", stream.read(4))[0]
        if alpha_size + color_size + 8 > data_size:
            raise ValueError(f"alpha_size({alpha_size:#010x}) + color_size({color_size:#010x}) + 8 > data_size({data_size:#010x})")

        stream.seek(self.header_size + 8)
        alpha_offset = 0
        pixel_idx = 0
        while alpha_offset + 2 <= alpha_size:
            count = struct.unpack("<h", stream.read(2))[0]
            alpha_offset += 2

            if count > 0:
                if alpha_offset + count > alpha_size:
                    raise ValueError(f"alpha data exceeds alpha_size({alpha_size:#010x}): alpha_offset({alpha_offset:#010x}), count({count:#010x})")
                for _ in range(count):
                    alpha = struct.unpack("<B", stream.read(1))[0]
                    alpha_offset += 1
                    image_data[pixel_idx // self.width, pixel_idx % self.width, 3] = alpha
                    pixel_idx += 1
            elif count < 0:
                if alpha_offset + 1 > alpha_size:
                    raise ValueError(f"alpha data exceeds alpha_size({alpha_size:#010x}): alpha_offset({alpha_offset:#010x}), count({count:#010x})")
                alpha = struct.unpack("<B", stream.read(1))[0]
                alpha_offset += 1
                repeat_count = (count & 0x7FFF) + 1
                for _ in range(repeat_count):
                    image_data[pixel_idx // self.width, pixel_idx % self.width, 3] = alpha
                    pixel_idx += 1
            else:
                raise ValueError(f"invalid alpha count: {count}")
            
        if pixel_idx != self.width * self.height:
            raise ValueError(f"alpha data does not fill the entire image: alpha pixels count({pixel_idx}), width({self.width}), height({self.height})")

        stream.seek(self.header_size + alpha_size + 12)
        color_offset = 0
        pixel_idx = 0
        while color_offset + 1 <= color_size:
            ctrl_byte = struct.unpack("<B", stream.read(1))[0]
            color_offset += 1

            ctrl_flag = ctrl_byte & 0xC0
            count = ctrl_byte & 0x3F

            if ctrl_flag == 0x00:
                if color_offset + count * 3 > color_size:
                    raise ValueError(f"color data exceeds color_size({color_size:#010x}): color_offset({color_offset:#010x}), control flag({ctrl_flag:#02x}), count({count:#010x})")
                for _ in range(count):
                    bgr = struct.unpack("<BBB", stream.read(3))
                    color_offset += 3
                    image_data[pixel_idx // self.width, pixel_idx % self.width, 0:3] = bgr[::-1]
                    pixel_idx += 1
            elif ctrl_flag == 0x40:
                ## 此处实际输出像素为count+1个像素
                if color_offset + 3 > color_size:
                    raise ValueError(f"color data exceeds color_size({color_size:#010x}): color_offset({color_offset:#010x}), control flag({ctrl_flag:#02x}), count({count:#010x})")
                bgr = struct.unpack("<BBB", stream.read(3))
                color_offset += 3
                for _ in range(count + 1):
                    image_data[pixel_idx // self.width, pixel_idx % self.width, 0:3] = bgr[::-1]
                    pixel_idx += 1
            elif ctrl_flag == 0x80:
                if pixel_idx == 0:
                    raise ValueError(f"delta mode cannot be used for the first pixel: color_offset({color_offset:#010x}), control flag({ctrl_flag:#02x}), count({count:#010x})")
                if color_offset + count * 2 > color_size:
                    raise ValueError(f"color data exceeds color_size({color_size:#010x}): color_offset({color_offset:#010x}), control flag({ctrl_flag:#02x}), count({count:#010x})")
                for _ in range(count):
                    delta = struct.unpack("<H", stream.read(2))[0]
                    color_offset += 2
                    image_data[pixel_idx // self.width, pixel_idx % self.width, 0:3] = image_data[(pixel_idx-1) // self.width, (pixel_idx-1) % self.width, 0:3] + self._mode1_delta_calc(delta)
                    pixel_idx += 1
            else:
                raise ValueError(f"invalid color control flag: {ctrl_flag:#02x}")

        if pixel_idx != self.width * self.height:
            raise ValueError(f"color data does not fill the entire image: color pixels count({pixel_idx}), width({self.width}), height({self.height})")

        alpha_data = image_data[:, :, 3]
        if np.any(alpha_data != 0):
            img = Image.fromarray(image_data, "RGBA")
        else:
            img = Image.fromarray(image_data[:, :, 0:3], "RGB")

        return img
        

    def mgd_convert_mode2(self):
        stream = self.stream
        stream.seek(self.header_size)

        data_size = struct.unpack("<i", stream.read(4))[0]
        data = stream.read(data_size)
        img = Image.open(BytesIO(data))
        img.load()
        return img


    def mgd_convert_opt(self, opt_path, format="png"):
        img = self.mgd_convert()
        img.save(opt_path, format=format)

    def get_size(self):
        current_offset = self.stream.tell()
        self.stream.seek(0, 2)
        size = self.stream.tell()
        self.stream.seek(current_offset)

        return size

    def _is_mgd_file(self) -> bool:
        self.stream.seek(0)
        file_signature = self.stream.read(4)
        return file_signature == b"MGD "

    def _body_size_check(self):
        file_size = self.get_size()
        expected_file_size = self.header_size + self.body_size

        if file_size < expected_file_size:
            raise ValueError(f"file size({file_size:#010x}) is less than expected({expected_file_size:#010x})")

    def _mode1_delta_calc(self, delta) -> np.ndarray:
        delta_type = delta & 0x8000
        if delta_type != 0:
            delta_r = (delta >> 10) & 0x1F
            delta_g = (delta >> 5) & 0x1F
            delta_b = delta & 0x1F
        else:
            delta_r = (delta >> 10) & 0xF
            delta_g = (delta >> 5) & 0xF
            delta_b = delta & 0xF
            if (delta & 0x4000) != 0:
                delta_r = -delta_r
            if (delta & 0x0200) != 0:
                delta_g = -delta_g
            if (delta & 0x0010) != 0:
                delta_b = -delta_b

        return np.array([delta_r, delta_g, delta_b], dtype=np.int8)
