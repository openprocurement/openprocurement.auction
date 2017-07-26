import json
import contextlib


class TestClient(object):
    """TODO: """

@contextlib.contextmanager
def put_test_doc(db, doc):
    id, rev = db.save(doc)
    yield id
    del db[id]
