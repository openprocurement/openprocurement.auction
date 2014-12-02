# -*- coding: utf-8 -*-
from couchdb.design import ViewDefinition


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
