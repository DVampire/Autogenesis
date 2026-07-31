#!/usr/bin/env python
# coding=utf-8

# Copyright 2024 The HuggingFace Inc. team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import ast
import asyncio
import base64
import importlib.metadata
import mimetypes
import keyword
import os
import re
import types
from functools import lru_cache
from pathlib import Path
from textwrap import dedent
from typing import Any, Dict, Tuple, Optional, Union, Iterable, Awaitable, List, TypeVar

T = TypeVar("T")

@lru_cache
def _is_package_available(package_name: str) -> bool:
    try:
        importlib.metadata.version(package_name)
        return True
    except importlib.metadata.PackageNotFoundError:
        return False

async def gather_with_concurrency(
    coros: Iterable[Awaitable[T]],
    max_concurrency: int = 10,
    return_exceptions: bool = False,
) -> List[Union[T, BaseException]]:
    """Run coroutines concurrently with a concurrency limit, and collect all results.

    Args:
        coros: An iterable of coroutines/awaitables to run.
        max_concurrency: Maximum number of coroutines to run at the same time.
        return_exceptions: If True, exceptions are returned in the results list
                           instead of being raised, mirroring asyncio.gather().

    Returns:
        List of results in the same order as the input coroutines.
    """
    sem = asyncio.Semaphore(max_concurrency)

    async def _runner(coro: Awaitable[T]) -> Union[T, BaseException]:
        async with sem:
            if return_exceptions:
                try:
                    return await coro
                except BaseException as e:  # noqa: BLE001
                    return e
            else:
                return await coro

    return await asyncio.gather(
        *(_runner(c) for c in coros),
        return_exceptions=False,  # handled inside _runner
    )

def encode_file_base64(file_path: str) -> str:
    with open(file_path, "rb") as f:
        data = f.read()
    return base64.b64encode(data).decode("utf-8")

def decode_file_base64(data_base64: str) -> bytes:
    return base64.b64decode(data_base64)

def make_file_url(file_path: str) -> str:
    mime_type, _ = mimetypes.guess_type(file_path)
    return f"data:{mime_type.lower()};base64,{encode_file_base64(file_path)}"
