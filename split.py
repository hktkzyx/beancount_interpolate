__author__ = 'Akuukis <akuukis@kalvis.lv'

import datetime
import re
import math

from beancount.core.amount import Amount, add, sub, mul, div
from beancount.core import data
from beancount.core.position import Position
from beancount.core.number import ZERO, D, round_to

from .check_aliases import check_aliases_entry
from .get_dates import get_dates
from .parse_params import parse_params

__plugins__ = ['split']

def distribute_over_duration(max_duration, total_value, MIN_VALUE):
    ## Distribute value over points. TODO: add new methods

    if(total_value > 0):
        def round_to(n):
            return math.floor(n*100)/100
    else:
        def round_to(n):
            return math.ceil(n*100)/100

    if(abs(total_value/max_duration) > abs(MIN_VALUE)):
        amountEach = total_value / max_duration
        duration = max_duration
    else:
        if(total_value > 0):
            amountEach = MIN_VALUE
        else:
            amountEach = -MIN_VALUE
        duration = math.floor( abs(total_value) / MIN_VALUE )

    amounts = [];
    accumulated_remainder = D(str(0));
    for i in range(duration):
        amounts.append( D(str(round_to(amountEach + accumulated_remainder))) )
        accumulated_remainder += amountEach - amounts[len(amounts)-1]

    return amounts


def get_entries(duration, closing_dates, entry, MIN_VALUE):

    all_amounts = [];
    for posting in entry.postings:
        all_amounts.append( distribute_over_duration(duration, posting.units.number, MIN_VALUE) )

    max_duration = 0;
    for i in all_amounts:
        max_duration = max(max_duration, len(i))

    firsts = []
    for amounts in all_amounts:
        firsts.append( abs(amounts[0]) )
    accumulator = firsts.index(max(firsts))

    remainder = D(str(0));
    new_transactions = []
    for i in range( min(len(closing_dates), max_duration) ):
        postings = []

        doublecheck = [];
        for p, posting in enumerate(entry.postings):
            if i < len(all_amounts[p]):
                doublecheck.append(all_amounts[p][i])
        should_be_zero = sum(doublecheck)
        if should_be_zero != 0:
            all_amounts[accumulator][i] -= D(str(should_be_zero))
            remainder += should_be_zero

        for p, posting in enumerate(entry.postings):
            if i < len(all_amounts[p]):
                postings.append(data.Posting(
                    account=posting.account,
                    units=Amount(all_amounts[p][i], posting.units.currency),
                    cost=None,
                    price=None,
                    flag=posting.flag,
                    meta=None))

        e = data.Transaction(
            date=closing_dates[i],
            meta=entry.meta,
            flag=entry.flag,
            payee=entry.payee,
            narration=entry.narration + ' (Generated by interpolate-split %d/%d)'%(i+1, duration), # TODO: SUFFIX
            tags={'split'}, # TODO: TAG
            links=entry.links,
            postings=postings)
        new_transactions.append(e)

    return new_transactions


def split(entries, options_map, config_string):
    """Add depreciation entries for fixed assets.  See module docstring for more
    details and example"""
    errors = []

    ## Parse config and set defaults
    config_obj = eval(config_string, {}, {})
    if not isinstance(config_obj, dict):
        raise RuntimeError("Invalid plugin configuration: should be a single dict.")
    ALIASES_BEFORE   = config_obj.pop('aliases_before'  , ['splitBefore'])
    ALIASES_AFTER    = config_obj.pop('aliases_after'   , ['splitAfter', 'split'])
    ALIAS_SEPERATOR  = config_obj.pop('aliases_after'   , '-')
    DEFAULT_PERIOD   = config_obj.pop('default_period'  , 'Month')
    DEFAULT_METHOD   = config_obj.pop('default_method'  , 'SL')
    MIN_VALUE        = config_obj.pop('min_value'       , 0.05)
    MAX_NEW_TX       = config_obj.pop('max_new_tx'      , 9999)
    SUFFIX           = config_obj.pop('suffix'          , ' (Generated by interpolate-split)')
    TAG              = config_obj.pop('tag'             , 'split')
    MIN_VALUE = D(str(MIN_VALUE))

    ## Filter transaction entries that have tag or meta or its posting has meta.
    newEntries = []
    trashbin = []
    for i, entry in enumerate(entries):

        if not hasattr(entry, 'postings'):
            continue

        # TODO: ALIASES_BEFORE
        params = check_aliases_entry(ALIASES_AFTER, entry, ALIAS_SEPERATOR)
        if not params:
            continue

        trashbin.append(entry)
        start, duration = parse_params(params, entry.date)
        closing_dates = get_dates(start, duration, MAX_NEW_TX)
        newEntries = newEntries + get_entries(duration, closing_dates, entry, MIN_VALUE)

    for trash in trashbin:
        entries.remove(trash)

    return entries + newEntries, errors
