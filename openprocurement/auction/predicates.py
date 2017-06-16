class HasKeys(object):
    def __init__(self, value):
        assert isinstance(value, (list, tuple))
        self.value = value

    def __call__(self, for_):
        return all((k in for_) for k in self.value)

    def phash(self):
        return 'HasKeys: {}'.format(self.value)

    text = phash


class ProcurementMethodType(object):

    def __init__(self, value, api):
        self.value = value

    def __call__(self, for_):
        return for_.get('procurementMethodType', '') == self.value

    def phash(self):
        return 'ProcurementMethodType: {}'.format(self.value)

    text = phash


class Status(object):

    def __init__(self, value):
        self.value = value

    def __call__(self, for_):
        return for_.get('status', '') == self.value

    def phash(self):
        return 'status: {}'.format(self.value)

    text = phash
