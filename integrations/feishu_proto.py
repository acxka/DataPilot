# -*- coding: utf-8 -*-
"""飞书长连接用的最小 Protobuf 编解码（pbbp2.Frame），零第三方依赖。

proto 定义（pbbp2.proto）：
  message Header { string key = 1; string value = 2; }
  message Frame {
    uint64 SeqID = 1; uint64 LogID = 2; uint64 service = 3; uint64 method = 4;
    repeated Header headers = 5; string payload_encoding = 6;
    string payload_type = 7; bytes payload = 8; string LogIDNew = 9;
  }
"""


def encode_varint(n):
    out = bytearray()
    n = int(n)
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _tag(field, wire):
    return encode_varint((field << 3) | wire)


def _field_varint(field, value):
    if value:
        return _tag(field, 0) + encode_varint(value)
    return b""


def _field_bytes(field, data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    if not data:
        return b""
    return _tag(field, 2) + encode_varint(len(data)) + data


def encode_header(key, value):
    return _field_bytes(1, key) + _field_bytes(2, value)


def encode_frame(seq_id=0, log_id=0, service=0, method=0, headers=None, payload=b"",
                 payload_encoding="", payload_type=""):
    # 注意：飞书 pbbp2.Frame 是 proto2 语义，0 值字段也必须显式编码（官方 SDK 序列化结果含 08 00 10 00 20 00）
    parts = [_tag(1, 0), encode_varint(seq_id), _tag(2, 0), encode_varint(log_id),
             _tag(3, 0), encode_varint(service), _tag(4, 0), encode_varint(method)]
    for k, v in (headers or []):
        parts.append(_field_bytes(5, encode_header(k, v)))
    parts.append(_field_bytes(6, payload_encoding))
    parts.append(_field_bytes(7, payload_type))
    parts.append(_field_bytes(8, payload))
    return b"".join(parts)


def _read_varint(buf, i):
    shift = 0
    result = 0
    while True:
        b = buf[i]
        i += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, i
        shift += 7


def _decode_headers(data):
    headers = {}
    i = 0
    n = len(data)
    while i < n:
        key, i = _read_varint(data, i)
        field, wire = key >> 3, key & 0x7
        if wire == 2:
            ln, i = _read_varint(data, i)
            raw = data[i:i + ln]
            i += ln
            if field == 1:
                cur_key = raw.decode("utf-8", "ignore")
            elif field == 2:
                headers[cur_key] = raw.decode("utf-8", "ignore")
        elif wire == 0:
            _, i = _read_varint(data, i)
        else:
            break
    return headers


def decode_frame(data):
    frame = {"seq": 0, "log_id": 0, "service": 0, "method": 0, "headers": {},
             "payload": b"", "payload_encoding": "", "payload_type": ""}
    i = 0
    n = len(data)
    while i < n:
        key, i = _read_varint(data, i)
        field, wire = key >> 3, key & 0x7
        if wire == 0:
            val, i = _read_varint(data, i)
            if field == 1:
                frame["seq"] = val
            elif field == 2:
                frame["log_id"] = val
            elif field == 3:
                frame["service"] = val
            elif field == 4:
                frame["method"] = val
        elif wire == 2:
            ln, i = _read_varint(data, i)
            raw = data[i:i + ln]
            i += ln
            if field == 5:
                frame["headers"].update(_decode_headers(raw))
            elif field == 6:
                frame["payload_encoding"] = raw.decode("utf-8", "ignore")
            elif field == 7:
                frame["payload_type"] = raw.decode("utf-8", "ignore")
            elif field == 8:
                frame["payload"] = raw
            elif field == 9:
                frame["log_id_new"] = raw.decode("utf-8", "ignore")
        elif wire == 1:
            i += 8
        elif wire == 5:
            i += 4
        else:
            break
    return frame