#!/usr/bin/env python

from setuptools import setup, find_packages

setup(
    name='netkan_indexer',
    version='1.0',
    description='NetKAN Indexer',
    author='Leon Wright',
    author_email='techman83@gmail.com',
    packages=find_packages(),
    package_data={
        "": ["*.txt", "*.jinja2", "*.graphql"],
    },
    install_requires=[
        'boto3',
        'click',
        'gitpython',
        'pynamodb',
        # 2019-11-01 capping to 2.8.0 - https://github.com/boto/botocore/commit/e87e7a745fd972815b235a9ee685232745aa94f9
        'python-dateutil>=2.1,<2.8.1',
        'requests',
        'flask',
        'jinja2',
        'internetarchive',
        'gunicorn>=19.9,!=20.0.0',
        'discord',
        'PyGithub',
    ],
    entry_points={
        'console_scripts': [
            'netkan=netkan.cli:netkan',
        ],
    },
    extras_require={
        'development': [
            'ptvsd',
            'pylint',
            'autopep8',
            'troposphere',
        ],
        'test': [
            'mypy',
        ]
    },
)
