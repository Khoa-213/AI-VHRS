"""Optional workstation password encrypted with Windows DPAPI for the current Windows user.

The encrypted file is scoped to the backend and technician account. Passwords
are never stored in source/config JSON; another Windows user cannot decrypt it.
"""
from __future__ import annotations

import ctypes
import getpass
import json
import os
from pathlib import Path

CREDENTIAL_FILE = Path(__file__).resolve().parents[1] / ".tech_credentials.dpapi"


class CredentialError(Exception):
    pass


class _Blob(ctypes.Structure):
    _fields_ = [("size", ctypes.c_uint32), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _dpapi(data: bytes, *, protect: bool) -> bytes:
    if os.name != "nt":
        raise CredentialError("Mật khẩu lưu trên máy trạm này cần Windows DPAPI.")
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    fn = crypt.CryptProtectData if protect else crypt.CryptUnprotectData
    fn.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.POINTER(_Blob),
                   ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(_Blob)]
    fn.restype = ctypes.c_int
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    buffer = ctypes.create_string_buffer(data)
    source = _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = _Blob()
    # Current-user encryption; disallow interactive Windows dialogs.
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise CredentialError(f"Windows không xử lý được mật khẩu đã mã hóa (mã {ctypes.get_last_error()}).")
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree(ctypes.cast(target.data, ctypes.c_void_p))


def _identity(backend_url: str, email: str) -> tuple[str, str]:
    return backend_url.rstrip("/"), email.strip().casefold()


def save_password(backend_url: str, email: str, password: str, *, path: Path = CREDENTIAL_FILE) -> None:
    if not password:
        raise CredentialError("Không lưu mật khẩu trống.")
    backend, account = _identity(backend_url, email)
    payload = json.dumps({"backend": backend, "email": account, "password": password}).encode("utf-8")
    encrypted = _dpapi(payload, protect=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_bytes(encrypted)
        temporary.replace(path)
    except OSError:
        raise CredentialError("Không lưu được mật khẩu đã mã hóa trên máy trạm.") from None


def load_password(backend_url: str, email: str, *, path: Path = CREDENTIAL_FILE) -> str | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(_dpapi(path.read_bytes(), protect=False).decode("utf-8"))
        if (payload["backend"], payload["email"]) != _identity(backend_url, email):
            return None
        password = payload["password"]
        if not isinstance(password, str) or not password:
            raise ValueError("empty credential")
        return password
    except (OSError, ValueError, KeyError, TypeError):
        raise CredentialError("Không đọc được file mật khẩu đã mã hóa trên máy trạm.") from None


def get_password(backend_url: str, email: str, explicit: str | None = None) -> str:
    password = explicit or load_password(backend_url, email) or os.environ.get("VHRS_TECH_PASSWORD")
    if not password:
        password = getpass.getpass(f"Mật khẩu của {email}: ")
    if not password:
        raise CredentialError("Chưa nhập mật khẩu.")
    return password
