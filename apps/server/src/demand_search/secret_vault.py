"""Windows current-user DPAPI. No plaintext fallback or machine-wide scope."""

import ctypes
import hashlib
import sys
from ctypes import wintypes

from .errors import AppError


class _Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _blob(data: bytes):
    buffer = ctypes.create_string_buffer(data)
    return _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))), buffer


class WindowsDPAPIVault:
    available = sys.platform == "win32"
    storage_name = "windows_dpapi_current_user"

    def __init__(self):
        if not self.available:
            return
        self._crypt = ctypes.WinDLL("crypt32", use_last_error=True)
        self._kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        args = [
            ctypes.POINTER(_Blob),
            ctypes.c_void_p,
            ctypes.POINTER(_Blob),
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(_Blob),
        ]
        self._crypt.CryptProtectData.argtypes = args
        self._crypt.CryptProtectData.restype = wintypes.BOOL
        self._crypt.CryptUnprotectData.argtypes = args
        self._crypt.CryptUnprotectData.restype = wintypes.BOOL
        self._kernel.LocalFree.argtypes = [ctypes.c_void_p]
        self._kernel.LocalFree.restype = ctypes.c_void_p

    def _transform(self, raw: bytes, context: str, decrypt: bool) -> bytes:
        if not self.available:
            raise AppError(
                "SECRET_STORAGE_UNAVAILABLE", "当前仅支持 Windows 本地安全密钥存储。", 503
            )
        if not context or len(context) > 512 or not raw or len(raw) > 32768:
            raise AppError("SECRET_STORAGE_INVALID", "密钥保护数据无效。")
        source, source_buf = _blob(raw)
        entropy, entropy_buf = _blob(
            hashlib.sha256(
                ("Demand Search App / local-dev / v1 / " + context).encode("utf-8")
            ).digest()
        )
        output = _Blob()
        function = self._crypt.CryptUnprotectData if decrypt else self._crypt.CryptProtectData
        try:
            # CRYPTPROTECT_UI_FORBIDDEN only. Never CRYPTPROTECT_LOCAL_MACHINE.
            if not function(
                ctypes.byref(source),
                None,
                ctypes.byref(entropy),
                None,
                None,
                1,
                ctypes.byref(output),
            ):
                raise AppError(
                    "SECRET_STORAGE_FAILED",
                    "Windows 无法保护或解密此配置，请在原用户环境重试或重新输入密钥。",
                    503,
                )
            return ctypes.string_at(output.data, output.size)
        finally:
            ctypes.memset(source_buf, 0, len(source_buf))
            ctypes.memset(entropy_buf, 0, len(entropy_buf))
            if output.data:
                ctypes.memset(output.data, 0, output.size)
                self._kernel.LocalFree(output.data)

    def seal(self, secret: str, context: str) -> bytes:
        if not isinstance(secret, str) or not 1 <= len(secret) <= 8192:
            raise AppError("SECRET_STORAGE_INVALID", "密钥长度无效。")
        return (b"DSA-DPAPI-1" + bytes([0])) + self._transform(
            secret.encode("utf-8"), context, False
        )

    def unseal(self, blob: bytes, context: str) -> str:
        prefix = b"DSA-DPAPI-1" + bytes([0])
        if not isinstance(blob, bytes) or not blob.startswith(prefix):
            raise AppError("SECRET_STORAGE_INVALID", "不支持此密钥存储格式。")
        try:
            return self._transform(blob[len(prefix) :], context, True).decode("utf-8")
        except UnicodeError:
            raise AppError("SECRET_STORAGE_INVALID", "密钥保护数据无效。") from None
