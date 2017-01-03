# -*- coding: utf-8 -*-
from jinja2 import Template, Environment, PackageLoader
from json import loads

JINJA_ENV = Environment(loader=PackageLoader('openprocurement.auction',
                                             'templates'))

def prepare_initial_bid_stage(bidder_name="", bidder_id="", time="",
                              amount_features="", coeficient="", amount=""):
    stage = dict(bidder_id=bidder_id, time=str(time))
    stage["label"] = dict(
        en="Bidder #{}".format(bidder_name),
        ro="Licitant №{}".format(bidder_name),
        ru="Участник №{}".format(bidder_name)
    )

    stage['amount'] = amount if amount else 0
    if amount_features is not None and amount_features != "":
        stage['amount_features'] = str(amount_features)
    if coeficient:
        stage['coeficient'] = str(coeficient)
    return stage

prepare_results_stage = prepare_initial_bid_stage  # Looks identical

def prepare_bids_stage(exist_stage_params, params={}):
    exist_stage_params.update(params)
    stage = dict(type="bids", bidder_id=exist_stage_params['bidder_id'],
                 start=str(exist_stage_params['start']), time=str(exist_stage_params['time']))
    stage["amount"] = exist_stage_params['amount'] if exist_stage_params['amount'] else 0
    if 'amount_features' in exist_stage_params:
        stage["amount_features"] = exist_stage_params['amount_features']
    if 'coeficient' in exist_stage_params:
        stage["coeficient"] = exist_stage_params['coeficient']

    if exist_stage_params['bidder_name']:
        stage["label"] = {
            "en": "Bidder #{}".format(exist_stage_params['bidder_name']),
            "ru": "Участник №{}".format(exist_stage_params['bidder_name']),
            "ro": "Licitant №{}".format(exist_stage_params['bidder_name'])
        }
    else:
        stage["label"] = {
            "en": "",
            "ru": "",
            "ro": ""
        }
    return stage


def prepare_service_stage(**kwargs):
    pause = {
        "type": "pause",
        "start": ""
    }
    pause.update(kwargs)
    return pause


def get_template(name):
    return JINJA_ENV.get_template(name)
