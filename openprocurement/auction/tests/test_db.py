import pytest
import uuid
from couchdb import Server

from openprocurement.auction.design import sync_design_chronograph, sync_design
from openprocurement.auction.tests.unit.utils import test_public_document, put_test_doc


SERVER = Server('http://admin:zaq1xsw2@127.0.0.1:9000')


@pytest.fixture(scope='function')
def db(request):
    name = 'test_{}'.format(uuid.uuid4().hex)
    db = SERVER.create(name)
    sync_design_chronograph(db)
    sync_design(db)
    request.cls.db = db
    request.addfinalizer(lambda: SERVER.delete(name))
    return db


@pytest.mark.usefixtures('db')
class TestViews(object):

    def test_chronograph_view(self):
        with put_test_doc(self.db, test_public_document):
            data = next(iter(self.db.view('chronograph/start_date').rows))
            assert not set(data.get('value').keys()).difference(
                set(['start', 'mode', 'api_version', 'auction_type', 'procurementMethodType']))

    def test_start_date_view(self):
        """see: https://github.com/openprocurement/openprocurement.auction/blob/master/openprocurement/auction/design.py#L18"""

    def test_end_date_view(self):
        """see: https://github.com/openprocurement/openprocurement.auction/blob/master/openprocurement/auction/design.py#L8"""

    def test_pre_announce_view(self):
        """https://github.com/openprocurement/openprocurement.auction/blob/master/openprocurement/auction/design.py#L31"""
