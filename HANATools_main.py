import struct
import os
import sys
import copy
import re
import json

from HANATools_MSD import MsdCipher
from HANATools_MSD import MsdReader
import HANATools_MGD

##something like cli???
def main(argc, argv):
    if argc < 2:
        print(starttext)
        sys.exit(0)

    if not argv[1].startswith('-'):        
        print('请输入一个指令')
        sys.exit(1)

    CAs = []
    for i in range(1, argc):
        if argv[i].startswith('-'):
           if i > 1:
               CAs.append([cmd, copy.deepcopy(agm)])
           cmd = argv[i][1:]
           agm = []
        else:
            agm.append(argv[i])
    CAs.append([cmd, copy.deepcopy(agm)])
    
    mode = None
    input = None
    output_dir = None
    password = None
    encoding = None
    for ca in CAs:
        cmd = ca[0]
        if cmd == 'h':
            print(starttext + '\n' + helptext)
            sys.exit(0)
        elif cmd == 'm':
            if len(ca[1]) < 1:
                print(f'指令 -{cmd} 参数缺失')
                sys.exit(1)
            else:
                if mode == None:
                    mode = ca[1][0]
                else:
                    print('请勿重复指定模式')
                    sys.exit(1)
        elif cmd == 'i':
            if len(ca[1]) < 1:
                print(f'指令 -{cmd} 参数缺失')
                sys.exit(1)
            else:
                if input == None:
                    input = (0, ca[1][0])
        elif cmd == 'id':
            if len(ca[1]) < 1:
                print(f'指令 -{cmd} 参数缺失')
                sys.exit(1)
            else:
                if input == None:
                    input = (1, ca[1][0])
        elif cmd == 'od':
            if len(ca[1]) < 1:
                print(f'指令 -{cmd} 参数缺失')
                sys.exit(1)
            else:
                if output_dir == None:
                    output_dir = ca[1][0]
        elif cmd == 'pw':
            if len(ca[1]) < 1:
                print(f'指令 -{cmd} 参数缺失')
                sys.exit(1)
            else:
                if password == None:
                    password = ca[1][0]
        elif cmd == 'ec':
            if len(ca[1]) < 1:
                print(f'指令 -{cmd} 参数缺失')
                sys.exit(1)
            else:
                if encoding == None:
                    encoding = ca[1][0]
        else:
            print(f'未知指令：{cmd}')
            sys.exit(1)
                    
    IOs = []
    if output_dir == None:
        output_dir = 'opt'
    if input == None: 
        print('未指定输入')
        sys.exit(1)
    else:
        if input[0] == 0:
            if re.search(rf'([/\\])', input[1]) == None:
                output = os.path.join(output_dir, input[1])
            else:
                output = os.path.join(output_dir, re.split(rf'[/\\]', input[1])[-1])
            IOs.append((input[1], output))
        elif input[0] == 1:
            for root, dirs, files in os.walk(input[1]):  
                for file in files:
                    IOs.append((os.path.join(root, file), os.path.join(output_dir, root, file)))
                

    if mode == None:
        print('未指定模式')
        sys.exit(1)
    elif mode == '01' or mode == 'ufj':
        if password == None:
            for iop in IOs:
                extract_fjsys(iop[0], iop[1])
        else:
            for iop in IOs:
                extract_fjsys(iop[0], iop[1], password)
        sys.exit(0)
    elif mode == '03' or mode == 'umg':
        for iop in IOs:
            if iop[1].endswith(('.mgd', '.MGD')):
                mgd2png(iop[0], output_dir)
        sys.exit(0)
    elif mode == '05' or mode == 'msdl':
        for iop in IOs:
            if iop[1].endswith(('.msd', '.MSD')):
                if encoding == None:
                    msd_decode_light(iop[0], output_dir)
                else:
                    msd_decode_light(iop[0], output_dir, encoding)
        sys.exit(0)
    else:
        print(f'未知模式{mode}')
        sys.exit(1)





def is_fjsys_file(file_path):
    with open(file_path, 'rb') as f:
        header = f.read(5)
        return header == b'FJSYS'
    
def read_index(file):
    file.seek(0xC)
    names_size = struct.unpack('<I', file.read(4))[0]
    file_count = struct.unpack('<I', file.read(4))[0]
    
    file.seek(0x54 + file_count * 0x10)
    names_data = file.read(names_size)

    entries = []
    index_offset = 0x54    
    for i in range(file_count):
        file.seek(index_offset)
        name_offset = struct.unpack('<I', file.read(4))[0]
        size = struct.unpack('<I', file.read(4))[0]
        offset = struct.unpack('<Q', file.read(8))[0]
        if i < file_count - 1:
            file.seek(index_offset + 0x10)
            name_offset_next = struct.unpack('<I', file.read(4))[0]
            name_length = name_offset_next - name_offset - 1
            name = struct.unpack_from(f'{name_length}s', buffer=names_data, offset=name_offset)[0]
        else:
            name_length = names_size - name_offset - 2
            name = struct.unpack_from(f'{name_length}s', buffer=names_data, offset=name_offset)[0]
        name = name.decode('shift_jis')
        index_offset += 0x10
        entries.append((name, size, offset))    
    
    return entries

def save_file(output_dir, name, data):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    with open(os.path.join(output_dir, name), 'wb') as file:
        file.write(data)
    
def mgd2png(mgd_path, output_dir):
    png_path = os.path.join(output_dir, mgd_path[:-3] + 'png')
    MgdMeta = HANATools_MGD.read_metadata(mgd_path)

    if MgdMeta.mode == 0:
        img = HANATools_MGD.process_mode0(mgd_path, MgdMeta)
    elif MgdMeta.mode == 1:
        img = HANATools_MGD.process_mode1(mgd_path, MgdMeta)
    elif MgdMeta.mode == 2:
        img = HANATools_MGD.process_mode2(mgd_path, MgdMeta)
    else:
        raise ValueError(f"Unsupported mode {MgdMeta.mode}")
    png_optdir = png_path[:- len(re.split(rf'[/\\]', png_path)[-1])]
    if not os.path.exists(png_optdir):
        os.makedirs(png_optdir)
    img.save(png_path, format='PNG')
    #os.remove(mgd_path)

    return 0

def extract_fjsys(arc_path, output_dir, password=''):
    with open(arc_path, 'rb') as arc_file:
        if not is_fjsys_file(arc_path):
            raise ValueError("Invalid fjsys file")
        
        entries = read_index(arc_file)

        if len(entries) == 0:
            raise ValueError("No files found in this fjsys file")
        
        for entry in entries:
            name, size, offset = entry
            
            arc_file.seek(offset)
            data = arc_file.read(size)
            
            if name.endswith(('.msd', '.MSD')):
                cipher = MsdCipher(password)
                data = cipher.decrypt(data)
            #elif name.endswith(('.mgd', '.MGD')):
            #    pass
            
            save_file(output_dir, name, data)

    return 0

def msd_decode_light(msd_path, output_dir, encoding='utf8'):
    output_path = os.path.join(output_dir, msd_path[:-3] + 'json')
    reader = MsdReader(msd_path, encoding)
    reader.MsdReadLight()

    optdir = output_path[:- len(re.split(rf'[/\\]', output_path)[-1])]
    if not os.path.exists(optdir):
        os.makedirs(optdir)

    with open(output_path, 'w') as file:
        file.write(json.JSONEncoder().encode(reader.codes))

    return 0

starttext = '老引擎花吻资源包处理工具\n帮助文档见-h'

helptext = '''
-h  显示帮助文档

-m  指定工具模式，可用参数如下
    01 或 ufj   fjsys文件拆包
    03 或 umg   MGD文件转png
    05 或 msdl  MSD文件解码轻量版

-i  指定输入文件，暂不支持多个参数

-id 指定输入目录，暂不支持多个参数  会把此目录及其子目录下的所有文件作为输入文件

-od 指定输出目录，默认为opt

-pw 指定主密钥，只会在fjsys文件拆包中用来解密MSD文件，通常为对应作品的完整名称，中间可能会有空格，请用引号括起来

-ec 指定编码格式，只会用于MSD解码和编码(没做完)，默认为utf8
'''

main(len(sys.argv), sys.argv)
