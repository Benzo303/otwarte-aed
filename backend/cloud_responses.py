"""Strumieniowe odpowiedzi JSON i eksporty z porcjami do 32 KiB."""
import json
from fastapi.responses import StreamingResponse

def byte_chunks(payload,size=32768):
    for index in range(0,len(payload),size):yield payload[index:index+size]

def json_chunks(value):
    encoder=json.JSONEncoder(ensure_ascii=False,allow_nan=False,separators=(',',':'))
    buffer=bytearray()
    for piece in encoder.iterencode(value):
        view=memoryview(piece.encode('utf-8'))
        offset=0
        while offset<len(view):
            amount=min(32768-len(buffer),len(view)-offset)
            buffer.extend(view[offset:offset+amount]);offset+=amount
            if len(buffer)==32768:
                yield bytes(buffer);buffer.clear()
    if buffer:yield bytes(buffer)

def streamed_json(value):return StreamingResponse(json_chunks(value),media_type='application/json')
