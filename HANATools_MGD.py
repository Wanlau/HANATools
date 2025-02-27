import struct
from PIL import Image
import io
import copy

class MgdMetaData:
    def __init__(self, width, height, data_offset, unpacked_size, mode):
        self.width = width
        self.height = height
        self.data_offset = data_offset
        self.unpacked_size = unpacked_size
        self.mode = mode

def read_metadata(file_path):
    with open(file_path, 'rb') as f:
        header = f.read(0x1C)
        if len(header) < 0x1C or header[:4] != b'MGD ':
            raise ValueError("Invalid MGD file")
            
        header_size = struct.unpack('<H', header[4:6])[0]
        width = struct.unpack('<H', header[0xC:0xE])[0]
        height = struct.unpack('<H', header[0xE:0x10])[0]
        unpacked_size = struct.unpack('<i', header[0x10:0x14])[0]
        mode = struct.unpack('<h', header[0x18:0x1A])[0]
        
        return MgdMetaData(width, height, header_size, unpacked_size, mode)

##模式0 文件数据格式为BGRA32
def process_mode0(file_path, meta):

    with open(file_path, 'rb') as f:
        f.seek(meta.data_offset)
        data_size = struct.unpack('<I', f.read(4))[0]
        pixels = f.read(data_size)

    has_alpha = False
    for i in range(0, len(pixels), 4):
        if pixels[i+3] != 0:
            has_alpha = True
            break

    img = convert_mode0_to_image(pixels, has_alpha, meta.width, meta.height)
    
    return img

##模式1 某种压缩格式？
def process_mode1(file_path, meta):
    with open(file_path, 'rb') as f:
        f.seek(meta.data_offset)
        data_size = struct.unpack('<i', f.read(4))[0]
        data = f.read(data_size)
        
        decoder = MgdDecoder(data, meta)
        decoder.unpack()
        return Image.frombytes(decoder.format, (meta.width, meta.height), bytes(decoder.output))

##模式2 原始png文件加上mgd文件头（通常为0x60字节）
##去掉mgd文件头的部分后即可得原png文件
def process_mode2(file_path, meta):
    with open(file_path, 'rb') as f:
        f.seek(meta.data_offset)
        data_size = struct.unpack('<i', f.read(4))[0]
        png_data = f.read(data_size)
        return Image.open(io.BytesIO(png_data))
    
    
def convert_mode0_to_image(pixels, has_alpha, width, height):
    # 通道重排：BGR(A) → RGB(A)
    converted = bytearray(len(pixels))
    mode = 'RGBA' if has_alpha else 'RGB'
    for i in range(0, len(pixels), 4):
        converted[i]   = pixels[i+2]  # R
        converted[i+1] = pixels[i+1]  # G
        converted[i+2] = pixels[i]    # B
        converted[i+3] = pixels[i+3]  # A            
    
    if mode == 'RGB':
        converted_na = bytearray()
        for i in range(0, len(converted), 4):
            converted_na.append(converted[i])
            converted_na.append(converted[i+1])
            converted_na.append(converted[i+2])
        return Image.frombytes('RGB', (width, height), bytes(converted_na))
    else:
        return Image.frombytes('RGBA', (width, height), bytes(converted))
    
def clamp(value, min_val=0, max_val=255):
    return max(min_val, min(value, max_val))
    
## deepseekR1生成 但有大量删改
class MgdDecoder:
    def __init__(self, data, meta):
        self.data = io.BytesIO(data)
        self.meta = meta
        self.output = bytearray(meta.unpacked_size)
        self.format = 'RGBA'

    def unpack(self):
        alpha_size = struct.unpack('<i', self.data.read(4))[0]
        has_alpha = self._unpack_alpha(alpha_size)
        rgb_size = struct.unpack('<i', self.data.read(4))[0]
        self._unpack_color(rgb_size)

        ##BGRA转RGBA
        output = copy.deepcopy(self.output)
        if has_alpha:
            for i in range(0,len(output), 4):
                self.output[i] = output[i+2]
                self.output[i+2] = output[i]
        else:
            self.format = 'RGB'            
            output_na = bytearray()
            for i in range(0,len(output), 4):
                output_na.append(output[i+2])
                output_na.append(output[i+1])
                output_na.append(output[i])
            self.output = output_na
            
    def _unpack_alpha(self, length):
        has_alpha = False
        dst = 3  # Alpha通道起始位置（BGRA格式的第4字节）
        remaining = length

        while remaining > 0:
            # 读取2字节的有符号计数
            count = struct.unpack('<h', self.data.read(2))[0]
            remaining -= 2

            if count < 0:  # RLE压缩模式
                # 取低15位并+1得到实际重复次数
                repeat_count = (count & 0x7FFF) + 1
                alpha = struct.unpack('<B', self.data.read(1))[0]
                remaining -= 1

                # 填充重复的Alpha值
                for _ in range(repeat_count):
                    self.output[dst] = alpha
                    dst += 4  # 每个像素占4字节
                has_alpha = has_alpha or (alpha != 0)

            else:  # 原始数据模式
                # 读取count个原始Alpha值
                alphas = self.data.read(count)
                remaining -= count
                for alpha in alphas:
                    a = struct.unpack('<B', alpha)[0]
                    self.output[dst] = a
                    dst += 4
                    has_alpha = has_alpha or (a != 0)

        return has_alpha
        
    def _unpack_color(self, length):
        dst = 0  # 颜色起始位置（BGRA的B分量）
        remaining = length

        while remaining > 0:
            # 读取控制字节
            ctrl_byte = struct.unpack('<B', self.data.read(1))[0]
            remaining -= 1

            flag = ctrl_byte & 0xC0  # 取高2位标志
            count = ctrl_byte & 0x3F  # 取低6位计数

            if flag == 0x80:  # 增量编码模式
                dst = self._process_delta_mode(count, dst)
                remaining -= count * 2  # 每个delta占2字节                

            elif flag == 0x40:  # 重复像素模式
                dst = self._process_repeat_mode(count, dst)
                remaining -= 3  # 基础像素占3字节

            elif flag == 0x00:  # 原始数据模式
                dst = self._process_raw_mode(count, dst)
                remaining -= count * 3  # 每个像素占3字节

            else:
                raise ValueError("无效的颜色块标志")

    def _process_delta_mode(self, count, dst):
        for _ in range(count):
            # 读取16位delta值
            delta = struct.unpack('<H', self.data.read(2))[0]

            # 获取前一个像素的RGB值
            prev_b = self.output[dst-4] if dst >=4 else 0
            prev_g = self.output[dst-3] if dst >=4 else 0
            prev_r = self.output[dst-2] if dst >=4 else 0

            # 解析delta值
            if delta & 0x8000:  # 使用5位增量
                r_add = (delta >> 10) & 0x1F
                g_add = (delta >> 5) & 0x1F
                b_add = delta & 0x1F
                new_r = prev_r + r_add
                new_g = prev_g + g_add
                new_b = prev_b + b_add
            else:               # 使用4位带符号增量
                r_sign = -1 if (delta & 0x4000) else 1
                r_add = r_sign * ((delta >> 10) & 0xF)

                g_sign = -1 if (delta & 0x0200) else 1
                g_add = g_sign * ((delta >> 5) & 0xF)

                b_sign = -1 if (delta & 0x0010) else 1
                b_add = b_sign * (delta & 0xF)

                new_r = prev_r + r_add
                new_g = prev_g + g_add
                new_b = prev_b + b_add

            # 写入新像素（BGR顺序）
            self.output[dst]   = clamp(new_b)
            self.output[dst+1] = clamp(new_g)
            self.output[dst+2] = clamp(new_r)
            dst += 4

            return dst
            

    def _process_repeat_mode(self, count, dst):
        # 读取基础像素
        base_b = struct.unpack('<B', self.data.read(1))[0]
        base_g = struct.unpack('<B', self.data.read(1))[0]
        base_r = struct.unpack('<B', self.data.read(1))[0]

        # 写入基础像素
        self.output[dst]   = base_b
        self.output[dst+1] = base_g
        self.output[dst+2] = base_r
        dst += 4

        # 重复count次
        for _ in range(count):
            self.output[dst]   = base_b
            self.output[dst+1] = base_g
            self.output[dst+2] = base_r
            dst += 4

        return dst

    def _process_raw_mode(self, count, dst):
        for _ in range(count):
            # 直接读取BGR三个通道
            b = struct.unpack('<B', self.data.read(1))[0]
            g = struct.unpack('<B', self.data.read(1))[0]
            r = struct.unpack('<B', self.data.read(1))[0]

            self.output[dst]   = b
            self.output[dst+1] = g
            self.output[dst+2] = r
            dst += 4

        return dst