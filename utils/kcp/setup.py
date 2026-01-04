"""
Build script for KCP Python extension.

Usage:
    cd utils/kcp
    python setup.py build_ext --inplace

Or with pip:
    pip install ./utils/kcp
"""

import sys
import os
from setuptools import setup, Extension

# Get the directory containing this file
here = os.path.abspath(os.path.dirname(__file__))

# Compiler flags
extra_compile_args = []
extra_link_args = []

if sys.platform == "win32":
    extra_compile_args = ["/O2", "/W3", "/std:c11", "/experimental:c11atomics"]
else:
    extra_compile_args = [
        "-O3",
        "-Wall",
        "-Wextra",
        "-Wno-unused-parameter",
        "-fvisibility=hidden",
    ]
    extra_link_args = ["-pthread"]

# Define the extension module
kcp_extension = Extension(
    "utils.kcp._kcp",
    sources=[
        os.path.join(here, "_kcp.c"),
        os.path.join(here, "ikcp.c"),
    ],
    include_dirs=[here],
    extra_compile_args=extra_compile_args,
    extra_link_args=extra_link_args,
    py_limited_api=False,
)

setup(
    name="utils-kcp",
    version="1.0.0",
    description="KCP Protocol Python Wrapper",
    author="byzp",
    ext_modules=[kcp_extension],
    packages=["utils.kcp"],
    package_dir={"utils.kcp": here},
    python_requires=">=3.10",
    zip_safe=False,
)
