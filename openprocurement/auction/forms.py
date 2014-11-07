from wtforms import Form, FloatField, StringField
from wtforms.validators import InputRequired, ValidationError, StopValidation
import wtforms_json
from .utils import get_latest_bid_for_bidder
wtforms_json.init()

################################################################################
#                                        Validators
################################################################################


def validate_bid_value(form, field):
    """
    Bid must be greater then 0
    """
    if field.data <= 0.0:
        raise ValidationError(u'To low value')


def validate_bid_change_on_bidding(form, field):
    """
    Bid must be lower then previous bidder bid amount minus minimalStep amount
    """
    stage_id = form.document['current_stage']
    minimal_bid = form.document['stages'][stage_id]['amount']
    if field.data > minimal_bid - form.document['minimalStep']['amount']:
        raise ValidationError(u'To high value')


def validate_bid_change_on_preliminary_bids(form, field):
    """
    Bid must be lower then all previous bids amount minus minimalStep amount
    """
    minimal_bid = get_latest_bid_for_bidder(form.document['initial_bids'],
                                            form.bidder_id.data)

    if field.data > (minimal_bid['amount'] - form.document['minimalStep']['amount']):
        raise ValidationError(u'To high value')


def validate_bidder_id_on_bidding(form, field):
    stage_id = form.document['current_stage']
    if field.data != form.document['stages'][stage_id]['bidder_id']:
        raise StopValidation(u'Not valid bidder')


def validate_bidder_id_on_preliminary_bids(form, field):
    if field.data not in [bid_info['bidder_id']
                          for bid_info in form.document['initial_bids']]:
        raise StopValidation(u'Not valid bidder')

################################################################################


class BidsForm(Form):
    bidder_id = StringField('bidder_id',
                            [InputRequired(message=u'No bidder id'), ])

    bid = FloatField('bid', [InputRequired(message=u'Bid amount is required'),
                             validate_bid_value])

    def validate_bid(form, field):
        stage_id = form.document['current_stage']
        if form.document['stages'][stage_id]['type'] == 'bids':
            validate_bid_change_on_bidding(form, field)
        elif form.document['stages'][stage_id]['type'] == 'preliminary_bids':
            validate_bid_change_on_preliminary_bids(form, field)
        else:
            raise ValidationError(u'Stage not for bidding')

    def validate_bidder_id(form, field):
        stage_id = form.document['current_stage']
        if form.document['stages'][stage_id]['type'] == 'bids':
            validate_bidder_id_on_bidding(form, field)
        elif form.document['stages'][stage_id]['type'] == 'preliminary_bids':
            validate_bidder_id_on_preliminary_bids(form, field)


