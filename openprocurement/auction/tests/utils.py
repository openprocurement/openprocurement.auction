import json
import contextlib


class TestClient(object):
    """TODO: """

with open('data/public_document.json') as _file:
    test_public_document = json.load(_file)


@contextlib.contextmanager
def put_test_doc(db, doc):
    id, rev = db.save(doc)
    yield id
    del db[id]
    

def update_start_auction_period(raw_data):
    """TODO: """
