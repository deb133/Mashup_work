from bs4 import BeautifulSoup
import geocoder
import json
import re
import requests
from collections import OrderedDict


INSPECTION_DOMAIN = 'http://info.kingcounty.gov'
INSPECTION_PATH = '/health/ehs/foodsafety/inspections/Results.aspx'
INSPECTION_PARAMS = {
    'Output': 'W',
    'Business_Name': '',
    'Business_Address': '',
    'Longitude': '',
    'Latitude': '',
    'City': '',
    'Zip_Code': '',
    'Inspection_Type': 'All',
    'Inspection_Start': '',
    'Inspection_End': '',
    'Inspection_Closed_Business': 'A',
    'Violation_Points': '',
    'Violation_Red_Points': '',
    'Violation_Descr': '',
    'Fuzzy_Search': 'N',
    'Sort': 'H'
}


def get_inspection_page(**kwargs):
	"""BUILD A DICT OF REQUEST QUERY PARAMETERS AND KEYWORDS (AN INSPECTION SERVICE)
	RETURNING ENCODED CONTECT AS A TUPLE"""
	url = INSPECTION_DOMAIN + INSPECTION_PATH
	params = INSPECTION_PARAMS.copy()
	for key, val in kwargs.items():
		if key in INSPECTION_PARAMS:
			params[key] = val
	resp = requests.get(url, params=params)
	resp.raise_for_status()
	return resp.content, resp.encoding


def parse_source(html, encoding='utf-8'):
	"""ANALYZE INTO ITS HTML PARTS"""
	parsed = BeautifulSoup(html, from_encoding=encoding)
	return parsed


def load_inspection_page(name):
	"""SAVE THE PARSED DATA AS A OUTPUT FILE"""
	with open(name, 'r') as fh:
		content = fh.read()
		return content, 'utf-8'


def restaurant_data_generator(html):
	"""WANT ONLY <DIV> TAGS THAT MATCH IDS THAT START WITH PR, WITH TAGS OF
	A CERTAIN NUMBER OF DIGITS AND END IN A TILDE CHARACTER"""
	id_finder = re.compile(r'PR[\d]+~')
	return html.find_all('div', id=id_finder)


def has_two_tds(elem):
	""" TAKES HTML AS ARGUMENT, VERIFIES IT HAS <TR> AND THEREFORE <TD>"""
	is_tr = elem.name == 'tr'
	td_children = elem.find_all('td', recursive=False)
	has_two = len(td_children) == 2
	return is_tr and has_two


def clean_data(td):
	"""STRIP WHITESPACES IN CELLS OF INSPECT ELEMENT OF WEB BROWSER
	AND CHARACTERS NOT NEEDED"""
	return unicode(td.text).strip(" \n:-")


def extract_restaurant_metadata(elem):
    """ITERATE THROUGH CLEAN ROWS OF DATA AND BUILD A DICTIONARY OF PAIRS"""	
    restaurant_data_rows = elem.find('tbody').find_all(
        has_two_tds, recursive=False
    )
    rdata = {}
    current_label = ''
    for data_row in restaurant_data_rows:
        key_cell, val_cell = data_row.find_all('td', recursive=False)
        new_label = clean_data(key_cell)
        current_label = new_label if new_label else current_label
        rdata.setdefault(current_label, []).append(clean_data(val_cell))
    return rdata


def is_inspection_data_row(elem):
	"""CATCH THE ROWS FOR THE CELLS THAT START NOT ONLY CONTAIN 
	THE WORD INSPECTION"""
	is_tr = elem.name == 'tr'
	if not is_tr:
		return False
	td_children = elem.find_all('td', recursive=False)
	has_four = len(td_children) == 4
	this_text = clean_data(td_children[0]).lower()
	contains_word = 'inspection' in this_text
	does_not_start = not this_text.startswith('inspection')
	return is_tr and has_four and contains_word and does_not_start


def get_score_data(elem):
	""" KEEP TRACK OF THE HIGHEST SCORE RECORDS OF THE INSPECTION DATA
	SUM OF TOTAL THE INSPECTIONS, CALCULATE AVERAGE, AND COUNT INSPECTIONS"""
	inspection_rows = elem.find_all(is_inspection_data_row)
	samples = len(inspection_rows)
	total = 0
	high_score = 0
	average = 0
	for row in inspection_rows:
		strval = clean_data(row.find_all('td')[2])
		try:
			intval = int(strval)
		except (ValueError, TypeError):
			samples -= 1
		else:
			total += intval
			high_score = intval if intval > high_score else high_score

	if samples:
		average = total/float(samples)
	data = {
	    u'Average Score': average,
	    u'High Score': high_score,
	    u'Total Inspections': samples
	}
	return data



def result_generator(count):
	""" GET TOP TEN RESULTS TO CONVERT FOR GEOCODING"""
	use_params = {
        'Inspection_Start': '2/1/2013',
        'Inspection_End': '2/1/2015',
        'Zip_Code': '98101'
    }
    # html, encoding = get_inspection_page(**use_params)
        html, encoding = load_inspection_page('inspection_page.html')
        parsed = parse_source(html, encoding)
        content_col = parsed.find("td", id="contentcol")
        data_list = restaurant_data_generator(content_col)
        for data_div in data_list[:count]:
            metadata = extract_restaurant_metadata(data_div)
            inspection_data = get_score_data(data_div)
            metadata.update(inspection_data)
            yield metadata
            #yield- make function a generator function- return iterator object
            #one result at a time


def get_geojson(result):
	""" GEOCODE RESULTS WITH GOOGLE MAPS AND RETURN- join the address"""
        address = " ".join(result.get('Address', ''))
        if not address:
            return None
        geocoded = geocoder.google(address)
        geojson = geocoded.geojson
        inspection_data = {}
        use_keys = (
            'Business Name', 'Average Score', 'Total Inspections', 'High Score'
        )
        for key, val in result.items():
            if key not in use_keys:
                continue
            if isinstance(val, list):
                val = " ".join(val)
            inspection_data[key] = val
        geojson['properties'] = inspection_data
        return geojson

def sort_geojson(result):
	"""sort the results by average, and highscore"""

	
if __name__ == '__main__':
    total_result = {'type': 'FeatureCollection', 'features': []}
    for result in result_generator(10):
        geojson = get_geojson(result)
        total_result['features'].append(geojson)
    with open('my_map.json', 'w') as fh:
        json.dump(total_result, fh)