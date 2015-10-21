# -*- coding: utf-8 -*-
from jinja2 import Template, Environment, PackageLoader
from json import loads

JINJA_ENV = Environment(loader=PackageLoader('openprocurement.auction',
                                             'templates'))

INITIAL_BIDS_TEMPLATE = Template(u'''{
    "bidder_id": "{{ bidder_id }}",
    "time": "{{ time }}",
    "label": {"en": "Bidder #{{ bidder_name }}",
              "ru": "Участник №{{ bidder_name }}",
              "uk": "Учасник №{{ bidder_name }}"},
    {% if amount_features %}"amount_features": "{{ amount_features}}",{% endif %}
    "amount": {% if amount %}{{ amount }}{% else %}null{% endif %}
}''')

PAUSE_TEMPLATE = Template(u'''{
    "type": "pause",
    "start": "{{ start }}"
}''')

BIDS_TEMPLATE = Template(u'''{
    "type": "bids",
    "bidder_id": "{{ bidder_id }}",
    "start": "{{ start }}",
    {% if bidder_name %}
    "label": {"en": "Bidder #{{ bidder_name }}",
              "ru": "Участник №{{ bidder_name }}",
              "uk": "Учасник №{{ bidder_name }}"},
    {% else %}
    "label": {"en": "",
              "ru": "",
              "uk": ""},
    {% endif %}
    "amount": {% if amount %}{{ amount }}{% else %}null{% endif %},
    {% if amount_features %}"amount_features": "{{ amount_features}}",{% endif %}
    "time": "{{ time }}"
}''')

ANNOUNCEMENT_TEMPLATE = Template(u'''{
    "type": "announcement",
    "start": "{{ start }}"
}''')


RESULTS_TEMPLATE = Template(u'''{
    "bidder_id": "{{ bidder_id }}",
    "label": {"en": "Bidder #{{ bidder_name }}",
              "ru": "Участник №{{ bidder_name }}",
              "uk": "Учасник №{{ bidder_name }}"},
    {% if amount_features %}"amount_features": "{{ amount_features}}",{% endif %}
    "amount": {% if amount %}{{ amount }}{% else %}null{% endif %},
    "time": "{{ time }}"
}''')


def generate_bids_stage(exist_stage_params, params):
    exist_stage_params.update(params)
    try:
      return loads(
          BIDS_TEMPLATE.render(**exist_stage_params)
      )
    except Exception, e:
      import pdb; pdb.set_trace() # ktarasz - Debug
      raise e


def generate_resuls(params):
    return loads(RESULTS_TEMPLATE.render(**params))


def get_template(name):
    return JINJA_ENV.get_template(name)
