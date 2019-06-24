#!/usr/bin/env python

from setuptools import setup, find_packages

setup(name='netkan-indexer',
    version='1.0',
    description='NetKAN Indexer',
    author='Leon Wright',
    author_email='techman83@gmail.com',
    packages=find_packages(),
    scripts=[
        'netkan-indexer.py',
    ],
    install_requires=[
        'boto3',
        'click',
        'gitpython',
    ],
)
