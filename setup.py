from setuptools import setup, find_packages
import os

version = '1.0'

setup(name='openprocurement.auction',
      version=version,
      description="",
      long_description=open("README.txt").read() + "\n" +
                       open(os.path.join("docs", "HISTORY.txt")).read(),
      # Get more strings from
      # http://pypi.python.org/pypi?:action=list_classifiers
      classifiers=[
        "Programming Language :: Python",
        ],
      keywords='',
      author='',
      author_email='',
      url='http://svn.plone.org/svn/collective/',
      license='GPL',
      packages=find_packages(exclude=['ez_setup']),
      namespace_packages=['op'],
      include_package_data=True,
      zip_safe=False,
      install_requires=[
          'setuptools',
          'requests',
          'APScheduler',
          'iso8601',
          'Flask'
          # -*- Extra requirements: -*-
      ],
      entry_points={
        'console_scripts': [
              'auction_worker = openprocurement.auction:main',
          ]
        }
      )
