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
        'flask',
        'internetarchive',
        'gunicorn',
    ],
    entry_points={
        'console_scripts': [
            'netkan=netkan.cli:netkan',
        ],
    },
    extras_require={
        'development': [
            'pytest',
            'ptvsd',
            'pylint',
            'autopep8',
            'troposphere'
        ]
    },
)
