"""Selective bounded member streaming from a seekable cached 7z archive.

The compressed file stays on disk (7z requires seeking); unrelated games are
never materialized. Each selected member is parsed/imported after its CRC check.
Requires py7zr 1.1.4's successful-member completion hook.
"""
from hashlib import sha256
from pathlib import PurePosixPath
import re
from threading import Lock
from tempfile import SpooledTemporaryFile
from time import perf_counter


def file_hash(path):
    digest=sha256()
    with open(path,'rb') as f:
        while chunk:=f.read(65536):digest.update(chunk)
    return digest.hexdigest()


def stream_members(path,day,on_member,*,max_member_bytes=5_000_000,max_total_bytes=128_000_000):
    import py7zr
    from py7zr.io import Py7zIO,WriterFactory
    match=re.compile(re.escape(day)+r'/(3|85)/(\d+)/prices$')
    stats={'total_uncompressed_bytes':0,'pokemon_uncompressed_bytes':0,'pokemon_members':0,
           'completed_members':0,'max_member_bytes':0,'parsing_seconds':0.0,'import_seconds':0.0,
           'extraction_mode':'seekable compressed file + CRC-checked per-member spool; unrelated games never extracted'}
    callback_lock=Lock()
    class Writer(Py7zIO):
        def __init__(self,name):
            self.name=name;self.buffer=SpooledTemporaryFile(max_size=1_000_000);self.length=0;self.done=False
        def write(self,data):
            end=self.buffer.tell()+len(data)
            if end>max_member_bytes:raise ValueError('Member exceeds configured bound')
            self.length=max(self.length,end);return self.buffer.write(data)
        def read(self,size=None):return self.buffer.read(-1 if size is None else size)
        def seek(self,offset,whence=0):return self.buffer.seek(offset,whence)
        def flush(self):self.buffer.flush()
        def size(self):return self.length
        def close(self):
            if self.done:return
            self.done=True
            try:
                self.buffer.seek(0);payload=self.buffer.read(max_member_bytes+1)
                if len(payload)>max_member_bytes:raise ValueError('Oversized member')
                with callback_lock:
                    on_member(self.name,payload,stats);stats['completed_members']+=1
                    stats['max_member_bytes']=max(stats['max_member_bytes'],len(payload))
            finally:self.buffer.close()
    class Factory(WriterFactory):
        def __init__(self):self.writers=[]
        def create(self,filename):
            if not match.fullmatch(filename):raise ValueError('Unselected archive member')
            writer=Writer(filename);self.writers.append(writer);return writer
        def cleanup(self):
            for writer in self.writers:
                if not writer.buffer.closed:writer.buffer.close()
    factory=Factory();started=perf_counter()
    try:
        with py7zr.SevenZipFile(path,'r') as archive:
            if tuple(int(x) for x in py7zr.__version__.split('.')[:3]) < (1,1,4):
                raise ValueError('py7zr >=1.1.4 required for CRC-success member completion')
            infos=archive.list()
            if len(infos)>50000:raise ValueError('Excessive archive members')
            targets=[]
            for item in infos:
                name=item.filename;p=PurePosixPath(name)
                if p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name or getattr(item,'is_symlink',False):
                    raise ValueError('Unsafe archive member')
                size=item.uncompressed or 0;stats['total_uncompressed_bytes']+=size
                if stats['total_uncompressed_bytes']>2_000_000_000:raise ValueError('Excessive total archive expansion')
                if match.fullmatch(name):
                    if size>max_member_bytes:raise ValueError('Oversized Pokemon member')
                    stats['pokemon_uncompressed_bytes']+=size;targets.append(name)
            if not targets or stats['pokemon_uncompressed_bytes']>max_total_bytes:raise ValueError('Invalid Pokemon archive selection/size')
            stats['pokemon_members']=len(targets)
            archive.extract(targets=targets,factory=factory)
            if stats['completed_members']!=len(targets):raise ValueError('Not all selected members completed')
    finally:factory.cleanup()
    stats['total_seconds']=perf_counter()-started
    # May include PPMd decode of unselected solid-block data; never claims CPU skips.
    return stats
