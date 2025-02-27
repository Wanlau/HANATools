import hashlib

class MsdCipher:
    def __init__(self, key):
        self.key = key
        self.block_num = 0
        self.block_size = 0x20
        
    def decrypt(self, data):
        output = bytearray()
        total_len = len(data)
        processed = 0

        # 处理完整块
        while processed + self.block_size <= total_len:
            chunk = data[processed : processed+self.block_size]
            self._process_chunk(chunk, output)
            processed += self.block_size

        # 处理最后不完整块
        if processed < total_len:
            remaining = data[processed:]
            self._process_chunk(remaining, output)

        return bytes(output)

    def _process_chunk(self, chunk: bytes, output: bytearray):
        chunk_key = f"{self.key}{self.block_num}".encode('shift_jis')
        md5_hash = hashlib.md5(chunk_key).hexdigest()  # 32字符
        for j in range(len(chunk)):  # 关键：按实际块长度循环
            output.append(chunk[j] ^ ord(md5_hash[j % 32])) 
        self.block_num += 1