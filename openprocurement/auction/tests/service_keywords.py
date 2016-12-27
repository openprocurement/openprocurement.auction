import json
import yaml
import sys
from openprocurement.auction.utils import calculate_hash

from robot.libraries.BuiltIn import BuiltIn
from Selenium2Library import utils

positions = [(0, 0), (960, 0), (0, 540), (960, 540)]
size = (960, 1000)

def prepare_tender_data():
    tender_file_path = BuiltIn().get_variable_value("${tender_file_path}")
    with open(tender_file_path) as tender_file:
        return json.load(tender_file)["data"]


def prepare_users_data(tender_data):
    auction_worker_defaults = BuiltIn().get_variable_value("${auction_worker_defaults}")
    with open(auction_worker_defaults) as auction_worker_defaults_file:
        auction_worker_defaults_info = yaml.load(auction_worker_defaults_file)
    users_data = {}
    for index, bid in enumerate(tender_data["bids"]):
        users_data[bid["id"]] = {
            'login_url': auction_worker_defaults_info['AUCTIONS_URL'].format(auction_id="11111111111111111111111111111111") +  '/login?bidder_id={}&hash={}'.format(
                bid["id"], calculate_hash(bid["id"], auction_worker_defaults_info["HASH_SECRET"])
            ),
            'amount': bid['value']['amount'],
            'position': positions[index],
            'size': size
        }
    return users_data


def convert_amount_to_number(amount_string):
    return float(amount_string.replace(' ', '').replace(',', '.'))


def Highlight_Element(locator):
    seleniumlib = BuiltIn().get_library_instance('Selenium2Library')
    element = seleniumlib._element_find(locator, True, True)
    seleniumlib._current_browser().execute_script("arguments[0].style['outline'] = '3px dotted red';", element)



def Clear_Highlight_Element(locator):
    seleniumlib = BuiltIn().get_library_instance('Selenium2Library')
    element = seleniumlib._element_find(locator, True, True)
    seleniumlib._current_browser().execute_script("arguments[0].style['outline'] = '';", element)

def Highlight_Elements_With_Text_On_Time(text, time=2):
    from time import sleep
    seleniumlib = BuiltIn().get_library_instance('Selenium2Library')
    locator = u"xpath=//*[contains(text(), {})]".format(utils.escape_xpath_value(text))
    elements = seleniumlib._element_find(locator, False, False)
    for element in elements:
        seleniumlib._current_browser().execute_script("arguments[0].style['outline'] = '3px dotted red';", element)
    sleep(time)
    for element in elements:
        seleniumlib._current_browser().execute_script("arguments[0].style['outline'] = '';", element)
