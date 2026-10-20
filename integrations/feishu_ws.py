# -*- coding: utf-8 -*-
"""最小 WebSocket 客户端（RFC 6455，纯标准库），用于飞书长连接。"""
import base64
import hashlib
import os
import socket
import ssl
import struct
import threading
import time
from urllib.parse import urlparse


class WebSocketError(Exception):
    pass


class WebSocket(object):
    def __init__(self, url, timeout=30):
        u = urlparse(url)
        if u.scheme not in ("wss", "ws"):
            raise WebSocketError("unsupported scheme: %s" % u.scheme)
        host = u.hostname
        port = u.port or (443 if u.scheme == "wss" else 80)
        path = u.path or "/"
        if u.query:
            path += "?" + u.query
        raw = socket.create_connection((host, port), timeout=timeout)
        if u.scheme == "wss":
            ctx = ssl.create_default_context()
            self.sock = ctx.wrap_socket(raw, server_hostname=host)
        else:
            self.sock = raw
        self.sock.settimeout(timeout)
        self._send_lock = threading.Lock()
        self._handshake(host, port, path)

    def _handshake(self, host, port, path):
        key = base64.b64encode(os.urandom(16)).decode()
        req = ("GET %s HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
               "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n") % (path, host, port, key)
        self.sock.sendall(req.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise WebSocketError("handshake closed by server")
            buf += chunk
        head, rest = buf.split(b"\r\n\r\n", 1)
        text = head.decode("utf-8", "ignore")
        if "101" not in text.split("\r\n")[0]:
            raise WebSocketError("handshake failed: %s" % text.split("\r\n")[0])
        accept = None
        for line in text.split("\r\n")[1:]:
            if line.lower().startswith("sec-websocket-accept:"):
                accept = line.split(":", 1)[1].strip()
        expected = base64.b64encode(hashlib.sha1(
            (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
        if accept != expected:
            raise WebSocketError("handshake accept mismatch")
        self._buf = rest

    def _read_exact(self, n):
        deadline = time.time() + 600
        while len(self._buf) < n:
            try:
                chunk = self.sock.recv(max(4096, n - len(self._buf)))
            except socket.timeout:
                if time.time() > deadline:
                    raise WebSocketError("read timeout")
                continue
            if not chunk:
                raise WebSocketError("connection closed")
            self._buf += chunk
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def send(self, data, opcode=0x2):
        if isinstance(data, str):
            data = data.encode("utf-8")
        header = bytearray([0x80 | opcode])
        ln = len(data)
        if ln < 126:
            header.append(0x80 | ln)
        elif ln < 65536:
            header.append(0x80 | 126)
            header += struct.pack(">H", ln)
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", ln)
        mask = os.urandom(4)
        header += mask
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        with self._send_lock:
            self.sock.sendall(bytes(header) + masked)

    def recv(self):
        """返回一条完整消息（自动处理 ping/pong/close 与分片）。"""
        message = b""
        while True:
            b1, b2 = self._read_exact(2)
            fin = b1 & 0x80
            opcode = b1 & 0x0F
            masked = b2 & 0x80
            ln = b2 & 0x7F
            if ln == 126:
                ln = struct.unpack(">H", self._read_exact(2))[0]
            elif ln == 127:
                ln = struct.unpack(">Q", self._read_exact(8))[0]
            mask = self._read_exact(4) if masked else None
            data = self._read_exact(ln)
            if mask:
                data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
            if opcode == 0x8:      # close
                raise WebSocketError("closed by server")
            if opcode == 0x9:      # ping -> pong
                self.send(data, opcode=0xA)
                continue
            if opcode == 0xA:      # pong
                continue
            message += data
            if fin:
                return message

    def close(self):
        try:
            self.send(b"", opcode=0x8)
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass