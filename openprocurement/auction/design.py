# -*- coding: utf-8 -*-
from couchdb.design import ViewDefinition
from couchdb.http import HTTPError
from time import sleep
from random import randint
import os


def add_index_options(doc):
    doc['options'] = {'local_seq': True}


start_date_chronograph = ViewDefinition(
    'chronograph',
    'start_date',
    open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'design_files/start_date.js')).read()
)


def sync_design_chronograph(db):
    views = [start_date_chronograph]
    ViewDefinition.sync_many(db, views, remove_missing=True, callback=add_index_options)


endDate_view = ViewDefinition(
    'auctions',
    'by_endDate',
    ''' function(doc) {
            var end = new Date(doc.endDate||doc.stages[0].start).getTime()
            emit(end, null);
        }
    '''
)

startDate_view = ViewDefinition(
    'auctions',
    'by_startDate',
    ''' function(doc) {
            var start = new Date(doc.stages[0].start).getTime()
            emit(start, null);
        }
    '''
)


PreAnnounce_view = ViewDefinition(
    'auctions',
    'PreAnnounce',
    ''' function(doc) {
            if ((doc.stages.length - 2) == doc.current_stage){
                emit(null, null);
            }
        }
    '''
)


def sync_design(db):
    views = [endDate_view, startDate_view, PreAnnounce_view]
    for view in views:
        view.sync(db)
    while True:
        design = db.get('_design/auctions')
        if not design:
            design = {'_id': '_design/auctions'}
        validate_doc_update = '''
        function(newDoc, oldDoc, userCtx, secObj) {
            if (userCtx.roles.indexOf('_admin') !== -1) {
                return true;
            } else {
                throw({forbidden: 'Only valid user may change docs.'});
            }
        }
        '''
        start_date_filter = '''function(doc, req) {
            var now = new Date();
            var start = new Date(((doc.stages||[])[0]||{}).start || '2000');
            if (start > now){
                return true;
            }
            return false;
        }
        '''
        if 'validate_doc_update' not in design or \
                validate_doc_update != design['validate_doc_update'] or \
                start_date_filter != design.get('filters', {}).get('by_startDate'):
            design['validate_doc_update'] = validate_doc_update
            design['filters'] = design.get('filters', {})
            design['filters']['by_startDate'] = start_date_filter
            try:
                return db.save(design)
            except HTTPError:
                sleep(randint(0, 2000) / 1000.0)
        else:
            return
