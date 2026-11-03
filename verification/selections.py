"""Versioned worker selections. Exact spans; semantic mappings are provisional.

This is an explicit bounded selection inventory, not a general-purpose claim parser.
Pilot omits recent-close sequence members; full adds those exact numerical assertions.
"""
import re

SOL_MARKET = {
    'sol-0530a9827c2c': {
        'structure': 'Daily highs and lows rise across the three supplied sessions.',
        'below_open': 'closes below both its opening price and the preceding session’s close',
        'volume': 'Reported volume increases across the sample',
        'range': 'Daily high-to-low ranges widen across the supplied candles.',
        'indicators': 'All seven indicator requests returned **unavailable**',
    },
    'sol-ab658b90eedc': {
        'structure': 'Across the three candles, daily highs and lows rise.',
        'below_open': 'the final candle closes below both its opening price and the previous session’s close',
        'volume': 'Reported volume increases across the supplied observations',
        'range': 'Daily high–low ranges widen',
        'indicators': 'All seven requested indicators are unavailable.',
    },
    'sol-efe11af8a17b': {
        'structure': 'The daily highs and lows progress upward.',
        'below_open': 'The final candle closes below its open and below the preceding close',
        'volume': 'Reported volume increases across the sample.',
        'indicators': 'Every requested indicator was reported unavailable.',
    },
}

NEWS = {
    'sol-0530a9827c2c': [
        'one unverified allegation of increased ETH demand',
        'The global-news digest repeats that same allegation; it is **not independent confirmation**.',
        'No macro series supplied in this synthetic snapshot.',
        'The Fed-rate-cut prediction-market query returned no evidence.',
    ],
    'sol-ab658b90eedc': [
        'an unverified claim of increased ETH demand',
        'The global-news digest repeats that same claim; it is **not independent corroboration**.',
        'No macro series supplied in this synthetic snapshot.',
        'The Fed-rate-cut prediction-market request returned **no evidence**.',
    ],
    'sol-efe11af8a17b': [
        'The only ETH-specific item alleges increased demand, but it is explicitly unverified',
        'The broader news digest repeats that same note; **it is not independent confirmation**.',
        'No macro series supplied in this synthetic snapshot.',
        'The prediction-market request likewise returned no evidence on Fed rate-cut probabilities.',
    ],
    'terra-2f66dbe7f15d': [
        'an alleged increase in ETH demand',
        'A separate synthetic digest repeats that same note; it is not a second source.',
        'The requested FRED series—CPI, core PCE, unemployment, the federal funds rate, the 10-year Treasury yield, the yield curve, and the VIX—were all unavailable in the snapshot.',
        'No prediction-market evidence was supplied for Fed cuts, recession, or Ethereum events.',
    ],
    'terra-f381dc458057': [
        'unverified allegation of increased ETH demand',
        'Because it has the same underlying synthetic source, **it is not a second confirmation**.',
        'Requests for CPI, core PCE, unemployment, the federal funds rate, the 10-year Treasury yield, the yield curve and VIX returned **no macro series**.',
        'Searches for Fed rate-cut, 2026 recession and Ethereum prediction markets returned **no probabilities**.',
    ],
    'terra-085765f41f69': [
        'a simulated desk note alleging increased ETH demand',
        'A separate synthetic global-news digest repeats that same note; it is **not a second source**.',
        'The requested CPI, core PCE, unemployment, federal funds rate, 10-year Treasury yield, and yield-curve series were all unavailable in the fixture.',
        'The prediction-market searches for Fed cuts, a 2026 recession, and Ethereum returned no evidence.',
    ],
}


def chosen(text, quote, rule, predicate, value, modality='asserted_observation', **extra):
    occurrences = list(re.finditer(re.escape(quote), text))
    if len(occurrences)!=1:
        raise ValueError(f'Selection must be unique: {rule}: {quote!r}, matches={len(occurrences)}')
    match = occurrences[0]
    return dict(start=match.start(), end=match.end(), rule=rule, predicate=predicate,
                value=value, modality=modality, **extra)


def select(report, text, profile):
    run = report['run_id']
    if report['field']=='final_trade_decision':
        yield chosen(text,'**Rating**: Hold','final.rating','paper_rating','Hold',modality='paper_recommendation',scope='this_run')
        yield chosen(text,'**Price Target**: not provided','final.target_missing','price_target_status','not_provided',modality='report_field_missingness',scope='this_run')
        yield chosen(text,'**Time Horizon**: not provided','final.horizon_missing','time_horizon_status','not_provided',modality='report_field_missingness',scope='this_run')
    elif report['field']=='news_report':
        allegation, duplicate, macro, prediction = NEWS[run]
        yield chosen(text,allegation,'news.allegation','demand_increase_alleged',True,modality='reported_unverified_allegation',evidence=['E_NEWS'],
                     assumptions=['An allegation is recorded; increased demand itself is not established.'])
        yield chosen(text,duplicate,'news.duplicate','digest_independent_confirmation',False,entity='synthetic_news_digest',evidence=['E_NEWS','E_GLOBAL'])
        yield chosen(text,macro,'news.macro_missing','requested_macro_series_status','not_supplied',entity='requested_macro_series',
                     modality='missing_data_observation',scope='this_run',evidence=['E_MACRO'])
        yield chosen(text,prediction,'news.prediction_missing','requested_event_probabilities_status','not_supplied',entity='requested_prediction_markets',
                     modality='missing_data_observation',scope='this_run',evidence=['E_PREDICTION'])
    elif report['field']=='market_report' and run in SOL_MARKET:
        q = SOL_MARKET[run]
        for column in ('High','Low'):
            yield chosen(text,q['structure'],'market.increasing_'+column.lower(),column.lower()+'_increasing',True,
                         valid_time={'start':'2026-10-26','end':'2026-10-28'}, evidence=['E_PRICE'],check='increasing',column=column)
        yield chosen(text,q['below_open'],'market.close_below_open','close_below_open',True,evidence=['E_PRICE'],check='below_open')
        yield chosen(text,q['below_open'],'market.close_below_previous','close_below_previous_close',True,evidence=['E_PRICE'],check='below_previous_close')
        yield chosen(text,q['volume'],'market.volume_increasing','volume_increasing',True,
                     valid_time={'start':'2026-10-26','end':'2026-10-28'},evidence=['E_PRICE'],check='increasing',column='Volume')
        if q.get('range'):
            yield chosen(text,q['range'],'market.range_increasing','intraday_range_increasing',True,
                         valid_time={'start':'2026-10-26','end':'2026-10-28'},evidence=['E_PRICE'],check='range_increasing')
        yield chosen(text,q['indicators'],'market.indicators_missing','requested_indicator_values_status','unavailable',
                     entity='requested_indicators',modality='missing_data_observation',scope='this_run',evidence=['E_INDICATOR'])
    elif report['field']=='market_report' and run.startswith('terra-'):
        # Five independently addressable OHLCV members from the first snapshot paragraph.
        paragraphs = text.split('\n\n')
        paragraph = next(p for p in paragraphs if '$2,550' in p and '$2,600' in p and '15,000' in p)
        left = text.index(paragraph)
        for column, amount, unit in [('open','2,550','USD'),('high','2,600','USD'),('low','2,510','USD'),('close','2,540','USD'),('volume','15,000','fixture_volume_units_unspecified')]:
            amount_match = next(re.finditer(re.escape(amount),paragraph))
            start, end = left+amount_match.start(), left+amount_match.end()
            yield dict(start=start,end=end,rule='market.ohlcv.'+column,predicate=column,value=amount.replace(',',''),
                       unit=unit,valid_time={'date':'2026-10-28'},modality='asserted_observation',
                       evidence=['E_PRICE','E_SNAPSHOT'],check='csv_value',
                       assumptions=['Entity/date/column resolved from enclosing snapshot paragraph; mapping awaits adjudication.'])
        if profile=='full':
            sequence_start = paragraph.index('recent closes') if 'recent closes' in paragraph else paragraph.index('three recent closes')
            sequence = paragraph[sequence_start:]
            for match, date in zip(re.finditer(r'2,(?:520|550|540)',sequence),['2026-10-26','2026-10-27','2026-10-28']):
                start, end = left+sequence_start+match.start(), left+sequence_start+match.end()
                yield dict(start=start,end=end,rule='market.recent_close.'+date,predicate='close',value=match.group().replace(',',''),
                           unit='USD',valid_time={'date':date},modality='asserted_observation',evidence=['E_PRICE','E_SNAPSHOT'],check='csv_value',
                           assumptions=['Date is explicit or candidate sequence-order mapping to fixture dates; awaits adjudication.'])
