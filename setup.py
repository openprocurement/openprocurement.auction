from setuptools import setup, find_packages
import os

version = '1.0.0.dev73'

setup(name='openprocurement.auction',
      version=version,
      description="",
      long_description=open("README.txt").read() + "\n" +
                       open(os.path.join("docs", "HISTORY.txt")).read(),
      # Get more strings from
      # http://pypi.python.org/pypi?:action=list_classifiers
      classifiers=[
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python",
      ],
      keywords='',
      author='Quintagroup, Ltd.',
      author_email='info@quintagroup.com',
      license='Apache License 2.0',
      url='https://github.com/openprocurement/openprocurement.auction',
      packages=find_packages(exclude=['ez_setup']),
      namespace_packages=['openprocurement'],
      include_package_data=True,
      zip_safe=False,
      install_requires=[
          'setuptools',
          'requests',
          'APScheduler',
          'iso8601',
          'python-dateutil',
          'Flask',
          'WTForms',
          'WTForms-JSON',
          'Flask-Redis',
          'WSGIProxy2',
          'gevent',
          'sse',
          'flask_oauthlib',
          'Flask-Assets',
          'cssmin',
          'jsmin',
          'PyYAML',
          'request_id_middleware'
      ],
      entry_points={
          'console_scripts': [
              'auction_worker = openprocurement.auction.auction_worker:main',
              'auctions_data_bridge = openprocurement.auction.databridge:main'
          ],
          'paste.app_factory': [
              'auctions_server = openprocurement.auction.auctions_server:make_auctions_app'
          ]
      },
      )
