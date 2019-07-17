#!/usr/bin/env python

from setuptools import setup, find_packages

setup(
    name='netkan_indexer',
    version='1.0',
    description='NetKAN Indexer',
    author='Leon Wright',
    author_email='techman83@gmail.com',
    packages=find_packages(),
    install_requires=[
        'boto3',
        'click',
        'gitpython',
        'pynamodb',
        # pynamodb requires it, but we're also leaning on it
        'python-dateutil',
        'requests',
    ],
    entry_points={
        'console_scripts': [
            'netkan-indexer=netkan.cli:indexer'
        ],
    },
)
