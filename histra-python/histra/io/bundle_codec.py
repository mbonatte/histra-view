"""Lossless, pickle-free encoding for content-addressed HiStrA arrays."""
from __future__ import annotations

import hashlib
import json
import math

import numpy as np

BUNDLE_FORMAT = "histra-results"
BUNDLE_VERSION = "1.0.0"
ARRAY_ENCODING = "byte-shuffle-v1"


def array_header(dtype, shape) -> bytes:
    return json.dumps([np.dtype(dtype).str, list(shape)], separators=(",", ":")).encode() + b"\0"


def array_digest(dtype, shape, raw) -> str:
    digest = hashlib.sha256(array_header(dtype, shape))
    digest.update(raw)
    return digest.hexdigest()


def array_descriptor(value):
    array = np.asarray(value)
    dtype = array.dtype
    if dtype.hasobject or dtype.fields or dtype.subdtype or dtype.itemsize == 0:
        raise ValueError(f"Unsupported bundle array dtype: {dtype}")
    raw = array.tobytes(order="C")
    descriptor = {"dtype": dtype.str, "shape": list(array.shape), "nbytes": len(raw)}
    return array_digest(dtype, array.shape, raw), descriptor, raw


def encode_array(raw: bytes, itemsize: int) -> bytes:
    """Group equal-significance bytes without changing any stored bit."""
    return np.frombuffer(raw, np.uint8).reshape(-1, itemsize).T.tobytes()


def validate_descriptor(descriptor):
    try:
        dtype = np.dtype(descriptor["dtype"])
        shape = descriptor["shape"]
        nbytes = descriptor["nbytes"]
        if dtype.hasobject or dtype.fields or dtype.subdtype or dtype.itemsize == 0:
            raise ValueError("unsupported dtype")
        if not isinstance(shape, list) or any(type(n) is not int or n < 0 for n in shape):
            raise ValueError("invalid shape")
        if type(nbytes) is not int or nbytes != math.prod(shape) * dtype.itemsize:
            raise ValueError("array byte length does not match dtype and shape")
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid .histra array descriptor: {exc}") from exc
    return dtype, tuple(shape), nbytes


def decode_array(payload: bytes, descriptor, expected_digest: str) -> np.ndarray:
    dtype, shape, nbytes = validate_descriptor(descriptor)
    if len(payload) != nbytes:
        raise ValueError("Bundle array payload length mismatch")
    raw = np.frombuffer(payload, np.uint8).reshape(dtype.itemsize, -1).T.copy()
    if array_digest(dtype, shape, memoryview(raw)) != expected_digest:
        raise ValueError(f"Bundle array checksum mismatch: {expected_digest}")
    return raw.view(dtype).reshape(shape)
