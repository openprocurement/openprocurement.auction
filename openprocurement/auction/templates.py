# -*- coding: utf-8 -*-
from jinja2 import Template
from json import loads

INITIAL_BIDS_TEMPLATE = Template(u'''{
    "bidder_id": "{{ bidder_id }}",
    "time": "{{ time }}",
    "label": {"en": "Bidder #{{ bidder_name }}",
              "ru": "Участник №{{ bidder_name }}",
              "uk": "Учасник №{{ bidder_name }}"},
    "amount": {{ amount }}
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
    "amount": {{ amount }},
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
    "amount": {{ amount }},
    "time": "{{ time }}"
}''')


def generate_bids_stage(exist_stage_params, params):
    exist_stage_params.update(params)
    return loads(
        BIDS_TEMPLATE.render(**exist_stage_params)
    )


def generate_resuls(params):
    return loads(RESULTS_TEMPLATE.render(**params))
