class KeyIn(object):
    def __init__(self, value, api):
        self.value = value

    def __call__(self, for_):
        return self.value in for_

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
