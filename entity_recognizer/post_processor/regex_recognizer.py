import re

from entity_recognizer.entity import Entity
from utils.text import get_context


def find_btc_adresses(plaintext):
    btc_adresses = []
    matches = re.findall(r"[13][a-km-zA-HJ-NP-Z1-9]{25,34}", plaintext)
    for match in matches:
        context = get_context(match, plaintext)
        entity = Entity("btc_adress", match, match, context)
        btc_adresses.append(entity)
    return btc_adresses


def find_bank_accounts(plaintext):
    ibans = []
    matches = re.findall(
        r'\b[A-Z]{2}\s*\d{2}\s*(?:\d\s*){4,20}\b',
        plaintext)
    for match in matches:
        context = get_context(match, plaintext)
        entity = Entity("bank_account", match, match, context)
        ibans.append(entity)
    return ibans

# TODO: rodne cisla
