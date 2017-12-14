class ProcurementMethodType(object):

    def __init__(self, value, api):
        self.value = value

    def __call__(self, for_):
        p_type = for_.get('procurementMethodType', 'default') or 'default'
        return p_type == self.value

    def phash(self):
        return 'ProcurementMethodType: {}'.format(self.value)

    text = phash
