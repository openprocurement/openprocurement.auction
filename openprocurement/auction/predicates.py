class ProcurementMethodType(object):

    def __init__(self, value, api):
        self.value = value

    def __call__(self, for_):
        return for_.get('procurementMethodType', '') == self.value

    def phash(self):
        return 'ProcurementMethodType: {}'.format(self.value)

    text = phash
