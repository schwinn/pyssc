"""For pip install."""

import setuptools
from os import path


# read the contents of your README file
this_directory = path.abspath(path.dirname(__file__))
with open(path.join(this_directory, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()


setuptools.setup(name='pyssc',
                 version="0.0.3",
                 setup_requires=['setuptools-git-versioning'],
                 description='Python Client fo Sennheiser Sound Control Protocol',
                 long_description=long_description,
                 long_description_content_type='text/markdown',
                 url='https://github.com/schwinn/pyssc',
                 author='JJ Wohlgemuth, Thorsten Schwinn',
                 author_email='',
                 license='MIT',
                 packages=setuptools.find_packages(),
                 package_data={'pyssc': []},
                 install_requires=['zeroconf'],
                 platforms='any',
                 python_requires='>=3.6',
                 classifiers=[
                     "Development Status :: 3 - Alpha",
                     "License :: OSI Approved :: MIT License",
                     "Operating System :: OS Independent",
                     "Programming Language :: Python",
                     "Programming Language :: Python :: 3",
                     "Programming Language :: Python :: 3 :: Only",
                     "Topic :: Multimedia :: Sound/Audio",
                 ],
                 zip_safe=True,
                 )
