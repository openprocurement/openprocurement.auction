import contextlib
from requests import Session as Sess
import signal, psutil
import os


@contextlib.contextmanager
def put_test_doc(db, doc):
    id, rev = db.save(doc)
    yield id
    del db[id]


class TestClient(Sess):
    def __init__(self, pref):
        super(self.__class__, self).__init__()
        self.pref = pref

    def get(self, url, **kwargs):
        return super(self.__class__, self)\
            .get('/'.join([self.pref, url]), **kwargs)


def kill_child_processes(parent_pid=os.getpid(), sig=signal.SIGTERM):
    try:
        parent = psutil.Process(parent_pid)
    except psutil.NoSuchProcess:
        return
    children = parent.children(recursive=True)
    for process in children:
        process.send_signal(sig)
