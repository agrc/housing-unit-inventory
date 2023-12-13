#!/usr/bin/env python
# -*- encoding: utf-8 -*-
"""
setup.py
A module that installs housing-unit-inventory as a module
"""
from glob import glob
from os.path import basename, splitext

from setuptools import find_packages, setup

setup(
    name="ugrc-housing-unit-inventory",
    version="1.0.0",
    license="",
    description="Analyze the housing inventory of a county or other geography",
    author="Josh Reynolds, WFRC; Jake Adams, UGRC",
    author_email="jdadams@utah.gov",
    url="https://github.com/agrc/housing-unit-inventory",
    packages=find_packages("src"),
    package_dir={"": "src"},
    py_modules=[splitext(basename(path))[0] for path in glob("src/*.py")],
    include_package_data=True,
    zip_safe=True,
    classifiers=[
        # complete classifier list: http://pypi.python.org/pypi?%3Aaction=list_classifiers
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Topic :: Utilities",
    ],
    project_urls={
        "Issue Tracker": "https://github.com/agrc/housing-unit-inventory/issues",
    },
    keywords=["gis"],
    install_requires=[
        "arcgis==2.2.*",
    ],
    extras_require={
        "tests": [
            "pytest-cov>=3,<5",
            "pytest-instafail==0.5.*",
            "pytest-mock==3.*",
            "pytest-ruff==0.*",
            "pytest-watch==4.*",
            "pytest>=6,<8",
            "black>=23.3,<23.12",
            "ruff==0.0.*",
        ]
    },
    setup_requires=[
        "pytest-runner",
    ],
    entry_points={
        "console_scripts": [
            "hui = housing_unit_inventory.main:process",
        ]
    },
)
