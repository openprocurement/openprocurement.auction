# -*- coding: utf-8 -*-
from couchdb.design import ViewDefinition
from couchdb.http import HTTPError
from time import sleep
from random import randint

endDate_view = ViewDefinition(
    "auctions",
    "by_endDate",
    ''' function(doc) {
            var end = new Date(doc.endDate).getTime()
            emit(end, null);
        }
    '''
)


def sync_design(db):
    views = [endDate_view]
    for view in views:
        view.sync(db)
    updated = False
    while not updated:
        design = db.get('_design/auctions')
        design['validate_doc_update'] = """
        function(newDoc, oldDoc, userCtx, secObj) {
            if (userCtx.roles.indexOf('_admin') !== -1) {
                return true;
            } else {
                throw({forbidden: 'Only valid user may change docs.'});
            }
        }
        """
        try:
            return db.save(design)
        except HTTPError, e:
            sleep(randint(0, 2000) / 1000.0)
