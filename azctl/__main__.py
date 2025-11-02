#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Azctl main module entry point.
Enables running azctl as a module: python -m azctl
"""

from .cli import main

if __name__ == "__main__":
    main()