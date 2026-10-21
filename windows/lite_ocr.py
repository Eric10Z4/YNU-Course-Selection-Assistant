# -*- coding: utf-8 -*-
"""
轻量验证码 OCR —— 仅依赖 PIL + numpy + onnxruntime
替代 ddddocr（85MB）+ opencv（112MB），模型仅 13MB
"""
import json
import numpy as np
from PIL import Image
import io
from desktop_support import find_resource

_charset = None
_session = None


def _res(name):
    return find_resource(name, __file__) or name


def _load():
    global _charset, _session
    if _session is not None:
        return
    import onnxruntime
    with open(_res("ocr_charset.json"), "r", encoding="utf-8") as f:
        _charset = json.load(f)
    _session = onnxruntime.InferenceSession(
        _res("ocr_model.onnx"),
        providers=["CPUExecutionProvider"])


def classification(img_bytes):
    _load()
    im = Image.open(io.BytesIO(img_bytes))
    if im.mode == "RGBA":
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[3])
        im = bg
    w, h = im.size
    new_w = int(w * (64 / h))
    im = im.resize((new_w, 64), Image.BILINEAR)
    im = im.convert("L")
    arr = np.array(im).astype(np.float32) / 255.0
    arr = arr[np.newaxis, np.newaxis, :, :]
    output = _session.run(None, {"input1": arr})[0]
    pred = np.argmax(output[:, 0, :], axis=1)
    result = []
    prev = -1
    for idx in pred:
        idx = int(idx)
        if idx != 0 and idx != prev and idx < len(_charset):
            result.append(_charset[idx])
        prev = idx
    return "".join(result)
