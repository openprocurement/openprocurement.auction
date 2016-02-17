from wtforms import Form, FloatField, StringField
from wtforms.validators import InputRequired, ValidationError, StopValidation
from fractions import Fraction
import wtforms_json
wtforms_json.init()

################################################################################
#                                        Validators
################################################################################


def validate_bid_value(form, field):
    """
    Bid must be greater then 0
    """
    if field.data <= 0.0 and field.data != -1:
        raise ValidationError(u'To low value')


def validate_bid_change_on_bidding(form, field):
    """
    Bid must be lower then previous bidder bid amount minus minimalStep amount
    """
    stage_id = form.document['current_stage']
    if form.auction.features:
        minimal_bid = form.document['stages'][stage_id]['amount_features']
        minimal = Fraction(minimal_bid) * form.auction.bidders_coeficient[form.data['bidder_id']]
        minimal -= Fraction(form.document['minimalStep']['amount'])
        if field.data > minimal:
            raise ValidationError(u'Too high value')
    else:
        minimal_bid = form.document['stages'][stage_id]['amount']
        if field.data > (minimal_bid - form.document['minimalStep']['amount']):
            raise ValidationError(u'Too high value')


def validate_bidder_id_on_bidding(form, field):
    stage_id = form.document['current_stage']
    if field.data != form.document['stages'][stage_id]['bidder_id']:
        raise StopValidation(u'Not valid bidder')


################################################################################


class BidsForm(Form):
    bidder_id = StringField('bidder_id',
                            [InputRequired(message=u'No bidder id'), ])

    bid = FloatField('bid', [InputRequired(message=u'Bid amount is required'),
                             validate_bid_value])

    def validate_bid(self, field):
        stage_id = self.document['current_stage']
        if self.document['stages'][stage_id]['type'] == 'bids':
            validate_bid_change_on_bidding(self, field)
        else:
            raise ValidationError(u'Stage not for bidding')

    def validate_bidder_id(self, field):
        stage_id = self.document['current_stage']
        if self.document['stages'][stage_id]['type'] == 'bids':
            validate_bidder_id_on_bidding(self, field)
