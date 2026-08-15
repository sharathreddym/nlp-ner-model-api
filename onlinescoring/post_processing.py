# from typing import Any
import os
import re
import pandas as pd
# import contractions
from thefuzz import fuzz
from thefuzz import process as process
import copy
import json
import ast

if "AZUREML_MODEL_DIR" in os.environ:
    base_path = os.getenv("AZUREML_MODEL_DIR")
else:
    # local
    base_path = "././"

valid_format = json.load(open(os.path.join(base_path, "dependencies/chemical_resistance.json")))

DEFAULT_TEMP = '23'
CHEM_RESISTANT_TAGS = {'chemical resistant'}

# Flat, independent lookups derived from valid_format.
# valid_format shape: {category: [{'sub_category', 'resistance_level', 'synonyms', 'temperature'}, ...]}
valid_categories = set(valid_format.keys())
valid_sub_categories = {
    cat: {item['sub_category'] for item in items}
    for cat, items in valid_format.items()
}
valid_resistance_levels = {
    (cat, item['sub_category']): item['resistance_level']
    for cat, items in valid_format.items()
    for item in items
}

# Reverse lookup: any known category / sub_category / synonym -> (category, sub_category or None)
chem_term_to_entry = {}
for cat, items in valid_format.items():
    chem_term_to_entry[cat] = (cat, None)
    for item in items:
        sub = item['sub_category']
        chem_term_to_entry[sub] = (cat, sub)
        for syn in item.get('synonyms', []):
            chem_term_to_entry[syn.strip().lower()] = (cat, sub)


def filler_percentage_to_numeric(value):
    """
    Identifies the filler percentage in the value and converts it to a numeric value.

    Note:
    - This function was used in older version of the model and currently not used.
    """

    try:
        value = re.sub('[^\d.,]', ' ', value)
        value = pd.to_numeric(value.split()[0])
    except:
        value = 0
    return value

def power_numbers_to_proper_format(power_number):
    """
    Converts power number expressions to proper numeric format.

    This function takes a string containing a power number expression (e.g. '10^6', '10 x 10^3') 
    and attempts to evaluate it into a proper numeric value.

    Parameters:
    -----------
    power_number : str
        A string containing a power number expression using x, ^, or ** notation

    Returns:
    --------
    str
        The evaluated numeric result as a string if successful, otherwise returns the original input string

    Examples:
    --------
    >> power_numbers_to_proper_format('10^6')
    '1000000'
    >> power_numbers_to_proper_format('10 x 10^3') 
    '10000'
    """

    try:
        return str(eval(power_number.replace(' ', '').replace('x', '*').replace('^','**')))
    except:
        return power_number

def string_to_number(value):
    """
    Converts a string to a numeric value.

    This function attempts to convert the input string to a numeric value using Python's eval function.
    If the conversion fails, it attempts to convert the string to a float.

    Parameters:
    -----------
    value : str
        The input string to be converted to a numeric value

    Returns:
    --------
    float
        The numeric value as a float if successful, otherwise returns the original input string
    """

    try:
        try: return eval(value)
        except: return float(value)
    except:
        return value
        
def modifier_unit_conversion_identifier(property_name, unit_to_search, possible_incoming_units, unit_conversion_table):
    """
    Identifies the appropriate unit conversion for a property modifier by matching against conversion tables.

    This function takes a property name and unit, matches it against possible incoming units using fuzzy matching,
    and returns the standardized unit (present in Chemille) and conversion formula if a match is found.

    Parameters:
    -----------
    property_name : str
        The name of the property being processed
    unit_to_search : str 
        The unit that needs to be converted
    possible_incoming_units : list
        List of possible incoming units to match against
    unit_conversion_table : pandas.DataFrame
        Table containing unit conversion mappings with columns:
        - Incoming Unit: Original unit
        - ceed_unit: Standardized unit present in Chemille/ceed table
        - formula: Formula to use for conversion

    Returns:
    --------
    tuple
        A tuple containing:
        - str or None: The standardized unit to convert to if match found, None otherwise
        - str or None: The conversion formula if match found, None otherwise
    """

    max_unit_score = process.extract(
        unit_to_search, possible_incoming_units, scorer=fuzz.token_sort_ratio, limit=1)[0]
    if max_unit_score[1] > 85:
        matched_raw = unit_conversion_table[unit_conversion_table['Incoming Unit']
                                            == max_unit_score[0]]
        print("Unit to be searched for: ", unit_to_search)
        print("Matched unit: ", max_unit_score[0])
        print("Score: ", max_unit_score[1])
        print("Convert to: ", matched_raw['ceed_unit'].values[0])
        print("Formula: ", matched_raw['formula'].values[0])
        return matched_raw['ceed_unit'].values[0], matched_raw['formula'].values[0]
    else:
        return None, None


def modifier_unit_conversion(properties_modifiers, DEPENDENCIES):
    """
    Converts property modifier units to standardized units (present in Chemille/Ceed) based on conversion tables.

    This function processes a list of property modifiers and converts their units to standardized units
    used in Chemille. It handles both general unit conversions and special exception cases for specific
    properties. The conversion is done using predefined conversion tables that map incoming units to 
    standardized units along with conversion formulas.

    Parameters:
    -----------
    properties_modifiers : list
        A list of dictionaries containing property information. Each dictionary should have:
        - property_name: Name of the property
        - modifier: Dictionary containing:
            - value: Property value
            - min: Minimum value (optional)
            - max: Maximum value (optional)
            - unit: Current unit of measurement
    
    DEPENDENCIES : dict
        Dictionary containing required data including:
        - UNIT_CONVERSION_TABLE_GENERAL: DataFrame with general unit conversions formulas
        - UNIT_CONVERSION_TABLE_FOR_EXEPTIONS: DataFrame for special cases where unit conversions are reverse or different from general unit conversions

    Returns:
    --------
    properties_modifiers : list
        Modifies the properties_modifiers list in-place, updating unit and value fields
        with converted values where applicable.

    Logic:
    ------
    1. For each property modifier:
        - If unit is present and not in excluded list ["", "%","v","volt","volts","°c","c","d"]:
            a. Check if property needs special handling using fuzzy matching
            b. Apply appropriate conversion table (general or exceptions)
            c. If conversion formula exists:
                - Append new unit to existing unit with '<->' separator
                - Convert value using formula
                - Convert min/max values if present
    2. Special handling for:
        - Bulk density
        - Flexural modulus tape
        - Tensile modulus tape
        - Specific resistivity
        - Average particle size
        - Inclined plane tracking
    """
    
    possible_incoming_units_general = list(
        set(DEPENDENCIES["UNIT_CONVERSION_TABLE_GENERAL"]['Incoming Unit']))
    possible_incoming_units_general.sort(key=lambda s: len(s))

    possible_incoming_units_for_exeptions = list(
        set(DEPENDENCIES["UNIT_CONVERSION_TABLE_FOR_EXEPTIONS"]['Incoming Unit']))
    possible_incoming_units_for_exeptions.sort(key=lambda s: len(s))
    for property_info in properties_modifiers:
        if "unit" in property_info['modifier']:
            if property_info['modifier']['unit'] not in ["", "%","v","volt","volts","°c","c","d"]:
                similarity_with_exception_properties = process.extract(property_info['property_name'], [
                                                                       "bulk density","bulk density iso 60 (kg/m³)",\
                                                                        "fluxural modulus tape", "flexural modulus astm d 790 tape 0° (mpa)",\
                                                                        "tensile modulus tape","tensile modulus astm d 3039 m tape 0° (mpa)",\
                                                                        "specific resistivity",\
                                                                        "average particle size", "avg particle size", "average particle size laser scattering d50",\
                                                                        "inclined plane tracking","inclined-plane tracking"], scorer=fuzz.token_sort_ratio, limit=1)[0][1]
                exception_property_identified = similarity_with_exception_properties > 90 or \
                    (similarity_with_exception_properties > 80 and \
                      "tape" in property_info['property_name']) or \
                    (process.extract(property_info['property_name'], ["volume resistivity"], scorer=fuzz.token_sort_ratio, limit=1)[0][1] > 90 and\
                      "mm" in property_info['property_name'])
                if exception_property_identified:
                    new_unit, unit_conversion_formula = modifier_unit_conversion_identifier(
                        property_info['property_name'], property_info['modifier']['unit'], possible_incoming_units_for_exeptions, DEPENDENCIES["UNIT_CONVERSION_TABLE_FOR_EXEPTIONS"])
                else:
                    new_unit, unit_conversion_formula = modifier_unit_conversion_identifier(
                        property_info['property_name'], property_info['modifier']['unit'], possible_incoming_units_general, DEPENDENCIES["UNIT_CONVERSION_TABLE_GENERAL"])

                #print(new_unit)
                if not exception_property_identified and property_info['modifier']['unit'] in ["mm"]:
                    unit_conversion_formula == None
                if unit_conversion_formula != None:
                    if property_info['modifier']['unit'] != "".join(new_unit.lower().split()):
                        property_info['modifier']['unit'] += '<->'+new_unit
                    try:
                        property_info['modifier']['value'] = str(round(string_to_number(
                            unit_conversion_formula.replace('x', str(property_info['modifier']['value']))),2))
                    except:
                        pass
                    try:
                        if property_info['modifier']['min']!=None:
                            property_info['modifier']['min'] = str(round(string_to_number(
                                unit_conversion_formula.replace('x', str(property_info['modifier']['min']))),2))
                    except:
                        pass
                    try:
                        if property_info['modifier']['max']!=None:
                            property_info['modifier']['max'] = str(round(string_to_number(
                                unit_conversion_formula.replace('x', str(property_info['modifier']['max']))),2))
                    except:
                        pass
        else:
            property_info['modifier']['unit'] = ''
    return properties_modifiers

def validate_property(properties): 
    """
    Validates the structure of the property dictionary.

    This function checks if each property in the list is a dictionary and contains the required keys.
    It also ensures that the 'modifier' dictionary within each property contains the necessary keys and values.
    """

    for prop in properties:  
        if not isinstance(prop, dict):  
            return False, "Each item in 'PROPERTY' must be a dictionary"  
        if 'property_name' not in prop or 'modifier' not in prop or 'property_type' not in prop:  
            return False, "Each property dictionary must contain 'property_name', 'modifier', and 'property_type' keys"  
        if not isinstance(prop['modifier'], dict):  
            return False, "'modifier' must be a dictionary"  
        for key in ['unit', 'value', 'min', 'max']:  
            if key not in prop['modifier']:  
                print(f"Missing key '{key}' in modifier" )
                prop['modifier'][key]=None
            elif key!='unit' and prop['modifier'][key]:
                unit_value = prop['modifier']['unit']
                if unit_value in prop['modifier'][key]:
                    prop['modifier'][key] = prop['modifier'][key].replace(unit_value,"")
    return True, "" 

def validate_filler(fillers): 
    """
    Validates the structure of the filler dictionary.

    This function checks if each filler in the list is a dictionary and contains the required keys.
    It also ensures that the 'filler_name' or 'total_load' keys are present and of the correct type.
    """

    for filler in fillers:  
        if not isinstance(filler, dict):  
            return False, "Each item in 'FILLER' must be a dictionary"  
        if 'filler_name' in filler:  
            if not isinstance(filler['filler_name'], list):  
                return False, "'filler_name' must be a list"  
        elif 'total_load' in filler:  
            if not isinstance(filler['total_load'], dict):  
                return False, "'total_load' must be a dictionary"  
            for key in ['value', 'min', 'max']:  
                if key not in filler['total_load']:  
                    return False, f"Missing key '{key}' in total_load"  
        else:  
            return False, "Each filler dictionary must contain either 'filler_name' or 'total_load'" 
    return True, "" 

def validate_auto_cert(auto_certs):  
    """
    Validates the structure of the auto certification dictionary.

    This function checks if each auto certification in the list is a dictionary and contains the required keys.
    It also ensures that the 'oem' and 'certs' keys are present and of the correct type.
    """
    
    new_auto_certs =[]
    certs_to_remove = []
    for cert in auto_certs:  
        if not isinstance(cert, dict) and isinstance(cert, str): 
            certs_to_remove.append(cert) 
            new_auto_certs.append({'oem': cert, 'certs': ['all']}) 
        elif 'oem' not in cert or 'certs' not in cert:  
            return False, "Each auto cert dictionary must contain 'oem' and 'certs'"  
        elif not isinstance(cert['certs'], list):  
            return False, "'certs' must be a list"  
        elif cert["oem"]==[]:
            cert["oem"]=["all"]
        elif cert["certs"]==[]:
            cert["certs"]=["all"]
    for cert in certs_to_remove:
        auto_certs.remove(cert) 
    for cert in new_auto_certs:
        auto_certs.append(cert) 
    return True, ""  
  
def validate_railway_cert(railway_certs):  
    """
    Validates the structure of the railway certification dictionary.

    This function checks if each railway certification in the list is a dictionary and contains the required keys.
    It also ensures that the 'standard', 'hazard_level', and 'req_set' keys are present and of the correct type.
    """

    for cert in railway_certs:  
        if not isinstance(cert, dict):  
            return False, "Each item in 'RAILWAY_CERT' must be a dictionary"  
        if 'standard' not in cert or 'hazard_level' not in cert or 'req_set' not in cert:  
            return False, "Each railway cert dictionary must contain 'standard', 'hazard_level', and 'req_set'"  
        if not isinstance(cert['hazard_level'], list) or not isinstance(cert['req_set'], list):  
            return False, "'hazard_level' and 'req_set' must be lists"  
    return True, ""  
  
def validate_water_cert(water_certs):  
    """
    Validates the structure of the water certification dictionary.

    This function checks if each water certification in the list is a dictionary and contains the required keys.
    It also ensures that the 'standard' and 'temp' keys are present and of the correct type.
    """

    for cert in water_certs:  
        if not isinstance(cert, dict):  
            return False, "Each item in 'WATER_CERT' must be a dictionary"  
        if 'standard' not in cert or 'temp' not in cert:  
            return False, "Each water cert dictionary must contain 'standard' and 'temp'"  
        if not isinstance(cert['temp'], list):  
            return False, "'temp' must be a list"  
    return True, ""  
  
def validate_nsf_cert(nsf_certs):  
    """
    Validates the structure of the NSF certification list.

    This function checks if each NSF certification is a list.
    """

    if not isinstance(nsf_certs, list):  
        return False, "'NSF_CERT' must be a list"  
    return True, ""  

def validate_chemical_resistance(chemical_resistances):
    """
    Validates the structure of the chemical resistance list.

    This function checks if each chemical resistance is a list.
    """

    if not isinstance(chemical_resistances, list):  
        return False, "'CHEMICAL_RESISTANCE' must be a list"  
    return True, ""

def validate_chemical_resistance_values(output):
    """Validate each field of every CHEMICAL_RESISTANCE entry independently.

    - category, sub_category, resistance_level are checked against flat lookups.
    - Invalid category / sub_category become 'None'.
    - When category + sub_category are valid, resistance_level is backfilled
      to the canonical value from the lookup (each pair maps to exactly one).
    - temperature is always normalized to '23'.
    """
    if not isinstance(output, dict):
        try:
            output = ast.literal_eval(output)
        except (ValueError, SyntaxError):
            return output

    entries = output.get('CHEMICAL_RESISTANCE') or []
    cleaned = []
    for item in entries:
        cat = (item.get('chemical_category') or '').strip().lower()
        sub = (item.get('chemical_sub_category') or '').strip().lower()

        cat_ok = cat in valid_categories
        sub_ok = cat_ok and sub in valid_sub_categories[cat]

        cleaned.append({
            'chemical_category': cat if cat_ok else 'None',
            'chemical_sub_category': sub if sub_ok else 'None',
            'temperature': DEFAULT_TEMP,
            'resistance_level': valid_resistance_levels[(cat, sub)] if sub_ok else 'None',
        })
    output['CHEMICAL_RESISTANCE'] = cleaned
    return output


def _make_chem_res_entry(cat, sub):
    return {
        'chemical_category': cat,
        'chemical_sub_category': sub if sub else 'None',
        'temperature': DEFAULT_TEMP,
        'resistance_level': valid_resistance_levels.get((cat, sub), 'None') if sub else 'None',
    }


def _find_chem_terms_in_text(text):
    """Scan `text` for known chemical terms (category / sub_category / synonym).

    Longest term first so multi-word synonyms match before their shorter parts.
    If a specific sub_category matches for a category, the bare-category hit
    for that same category is dropped to avoid duplicate entries.
    """
    text = ' ' + text.lower() + ' '
    hits = []
    for term in sorted(chem_term_to_entry.keys(), key=len, reverse=True):
        if not term or term not in text:
            continue
        hits.append(chem_term_to_entry[term])
        text = text.replace(term, ' ')
    specific_cats = {c for c, s in hits if s}
    return [h for h in hits if h[1] is not None or h[0] not in specific_cats]


def reclassify_feature_to_chem_res(output, query=None):
    """Move chemical-resistance signals from FEATURE into CHEMICAL_RESISTANCE.

    - Any FEATURE entry that directly matches a known category / sub_category
      / synonym is moved.
    - The generic tag 'chemical resistant' is always removed from FEATURE.
      When `query` is provided and contains 'resistant', the tail of the
      query after the first 'resistant' occurrence is scanned for known
      chemical terms; matches are added to CHEMICAL_RESISTANCE.
    """
    output = copy.deepcopy(output)
    features = output.get('FEATURE', []) or []
    kept, inferred = [], []
    had_generic_tag = False

    for f in features:
        f_norm = f.strip().lower()
        if f_norm in CHEM_RESISTANT_TAGS:
            had_generic_tag = True
            continue
        hit = chem_term_to_entry.get(f_norm)
        if hit is None:
            kept.append(f)
            continue
        cat, sub = hit
        inferred.append(_make_chem_res_entry(cat, sub))

    if had_generic_tag and query:
        q_lower = query.lower()
        if 'resistant' in q_lower:
            tail = q_lower.partition('resistant')[2]
            for cat, sub in _find_chem_terms_in_text(tail):
                inferred.append(_make_chem_res_entry(cat, sub))

    output['FEATURE'] = kept
    output.setdefault('CHEMICAL_RESISTANCE', [])
    output['CHEMICAL_RESISTANCE'].extend(inferred)
    return output


def chem_res_from_query(query):
    """Build CHEMICAL_RESISTANCE entries directly from `query` by matching known
    categories / sub_categories / synonyms in the lookup, independent of the
    model output. Returns an empty list when no known term is found.
    """
    if not query:
        return []
    return [_make_chem_res_entry(cat, sub) for cat, sub in _find_chem_terms_in_text(query)]

def validate_medical_cert(medical_certs):
    """
    Validates the structure of the medical certification list.

    This function checks if each medical certification is a list.
    """

    if not isinstance(medical_certs, list):  
        return False, "'MEDICAL_CERT' must be a list"  
    return True, ""

valid_medical_certifications = ['dmf039998', 'dmf039999', 'dmf040000', 'dmf040001', 'dmf040002', 'dmf10904', 'dmf11559', 'dmf12719', 'dmf14007', 'dmf14844', 'dmf1500', 'dmf17690', 'dmf18092', 'dmf8356', 'dmf8464', 'dmf8779', 'maf1078', 'maf1079', 'maf1097', 'maf1704', 'maf1873', 'maf302', 'maf315', 'maf588']
normalized_unique_values_file_path = os.path.join(base_path, "dependencies/normalized_unique_values_for_grade_mapping.json")
with open(file=normalized_unique_values_file_path) as f:
    NORMALIZED_UNIQUE_VALUES = json.load(f)
med_certs = NORMALIZED_UNIQUE_VALUES['MEDICAL_CERT']
med_cert_lookup = {k.lower(): v for k, v in med_certs}
default_output = {'GRADE': [], 'APPLICATION': [], 'BRAND': [], 'POLYMER': [], 'PROPERTY': [], 'FILLER': [], 'FEATURE': [], 'PROCESSING': [], 'DELIVERY_FORM': [], 'COMPETITOR_GRADE': [], 'AUTO_CERT': [], 'RAILWAY_CERT': [], 'WATER_CERT': [], 'NSF_CERT': [], 'INDUSTRY': [], 'REGION': [], 'MEDICAL_CERT': [], 'CHEMICAL_RESISTANCE': []}

def _is_med_cert(s):
    s = s.lower()
    return s in med_cert_lookup or s.replace(" ", "") in valid_medical_certifications

def validate_medical_cert_values(output):
    val = copy.deepcopy(output)
    cleaned, invalid = [], False
    for i in list(val.get('MEDICAL_CERT', [])):
        if _is_med_cert(i):
            cleaned.append(i.replace('_', ' ') if '_' in i else i)
        else:
            invalid = True
    if invalid and not cleaned:
        val = copy.deepcopy(default_output)
        val['MEDICAL_CERT'] = [None]
    else:
        val['MEDICAL_CERT'] = cleaned
    return val

def validate_feature_for_med_cert(output):
    val = copy.deepcopy(output)
    kept, moved = [], []
    for i in val.get('FEATURE', []):
        if _is_med_cert(i):
            moved.append(i.replace('_', ' ') if '_' in i else i)
        else:
            kept.append(i)
    val['FEATURE'] = kept
    val.setdefault('MEDICAL_CERT', []).extend(moved)
    return val

def validate_result_dict(data):   
    """
    Validates and sanitizes a result dictionary containing various entities extracted from the search query by the NER model.

    This function performs validation and cleanup on the result dictionary, ensuring all required keys are present with correct types and valid content. It removes any
    unexpected keys or incorrect types and initializes missing keys with empty lists.

    Parameters
    ----------
    data : dict
        A dictionary containing the entities that the NER model can extract from the search query with the following keys:
        - GRADE: List of Celanese grades
        - APPLICATION: List of applications
        - BRAND: List of brand names
        - POLYMER: List of polymer types
        - PROPERTY: List of properties/UL. Each item in the list is a dictionary with 'property_name', 'modifier', and 'property_type' keys. Each modifier is a dictionary with 'value', 'min', 'max', and 'unit' keys.
        - FILLER: List of upto two dictionaries, one containing filler names (optional) and another containing total load (must). Total load is a dictionary with 'value', 'min', and 'max' keys.
        - FEATURE: List of features
        - PROCESSING: List of processing types
        - DELIVERY_FORM: List of delivery forms
        - COMPETITOR_GRADE: List of competitor grades
        - AUTO_CERT: List of auto certifications. Each item in the list is a dictionary with 'oem' and 'certs' keys.
        - RAILWAY_CERT: List of railway certifications. Each item in the list is a dictionary with 'standard', 'hazard_level', and 'req_set' keys.
        - WATER_CERT: List of water certifications. Each item in the list is a dictionary with 'standard' and 'temp' keys.
        - NSF_CERT: List of NSF certifications.
        - INDUSTRY: List of industries
        - REGION: List of regions
        - MATERIAL_ID: List of material IDs
        - MEDICAL_CERT: List of medical certifications
        - CHEMICAL_RESISTANCE: List of chemical resistance properties

    Returns
    -------
    Boolean: True
        The function modifies the input dictionary in-place rather than returning a value.

    Logic
    -----
    1. Removes any unexpected keys from the input dictionary
    2. Ensures all expected keys exist, initializing missing ones with empty lists
    3. Validates that all values are of the correct type (list)
    4. Converts dict values to single-item lists if needed
    5. Performs additional validation on specialized fields (PROPERTY, FILLER, etc.)
    """

    expected_format = {  
    'GRADE': list,  
    'APPLICATION': list,  
    'BRAND': list,  
    'POLYMER': list,  
    'PROPERTY': list,  
    'FILLER': list,  
    'FEATURE': list,  
    'PROCESSING': list,  
    'DELIVERY_FORM': list,  
    'COMPETITOR_GRADE': list,  
    'AUTO_CERT': list,  
    'RAILWAY_CERT': list,  
    'WATER_CERT': list,  
    'NSF_CERT': list, 
    'INDUSTRY': list,  
    'REGION': list,
    'MATERIAL_ID': list,
    'MEDICAL_CERT': list,
    'CHEMICAL_RESISTANCE': list
    }  
    
     
    # Find any entities in the input data that are not expected  
    unknown_entities = set(data.keys() - expected_format.keys())
      
    # if unknown_entities and not "CERTIFICATION" in unknown_entities:  
    if unknown_entities: 
        for unknown_entity in unknown_entities:
            del data[unknown_entity]

  
    # Check if all required keys are present and of the correct type  
    for key, expected_type in expected_format.items():  
        if key not in data:  
            data[key]=[] 
        if not isinstance(data[key], expected_type):  
            print(f"Key '{key}' is not of type {expected_type.__name__}")
            if isinstance(data[key], dict):
                print(f"Converting it to list")
                data[key]=[data[key]]
            else:
                data[key]=[]
    
    # Validate PROPERTY  
    valid, message = validate_property(data['PROPERTY'])  
    if not valid:  
        print(message)
        data['PROPERTY']=[]
    
    # Validate FILLER  
    valid, message = validate_filler(data['FILLER'])  
    if not valid:  
        print(message)
        data['FILLER']=[]

  
    # Validate AUTO_CERT  
    valid, message = validate_auto_cert(data['AUTO_CERT'])  
    if not valid:  
        print(message)
        data['AUTO_CERT']=[] 
  
    # Validate RAILWAY_CERT  
    valid, message = validate_railway_cert(data['RAILWAY_CERT'])  
    if not valid:  
        print(message)
        data['RAILWAY_CERT']=[]   
  
    # Validate WATER_CERT  
    valid, message = validate_water_cert(data['WATER_CERT'])  
    if not valid:  
        print(message)
        data['WATER_CERT']=[]  
  
    # Validate NSF_CERT  
    valid, message = validate_nsf_cert(data['NSF_CERT'])  
    if not valid:  
        print(message)
        data['NSF_CERT']=[] 

    # Validate CHEMICAL_RESISTANCE  
    valid, message = validate_chemical_resistance(data['CHEMICAL_RESISTANCE'])
    if not valid:  
        print(message)
        data['CHEMICAL_RESISTANCE']=[]

    # Validate MEDICAL_CERT  
    valid, message = validate_medical_cert(data['MEDICAL_CERT'])
    if not valid:  
        print(message)
        data['MEDICAL_CERT']=[]
  
    print("Validation successful")
    return True

def identify_out_of_scope_items(DEPENDENCIES, search_query_cleaned, result, user_type):
        """
        Identifies the entities that are considered out of scope based on predefined rules and dependencies.

        This function analyzes various entities (polymers, brands, grades, fillers and others) in the result dictionary and moves
        those that match entries in the OUT_OF_SCOPE_DATA dependency to the out_of_scope_output dictionary.

        Parameters:
        -----------
        DEPENDENCIES : dict
            Dictionary containing data including:
            - OUT_OF_SCOPE_DATA: Dict of lists containing out-of-scope entities
            - OOS_COLOR_CODE_PATTERN: Regex pattern for color codes
        search_query_cleaned : str
            The preprocessed search query string
        result : dict
            Dictionary (NER Model output) containing the identified entities with all the keys. Each key containing lists of identified entities

        Returns:
        --------
        dict
            A dictionary containing the OOS Data structure:
            {
                "active": bool,  # True if any out-of-scope items found
                "entities": {
                    "GRADE": list,  # Out of scope grades
                    "BRAND": list,  # Out of scope brands
                    "POLYMER": list,  # Out of scope polymers
                    "FILLER": list,  # Out of scope fillers
                    "OTHERS": list   # Other out of scope items like "bondable", "toyota", "fda", "amorphous", "fmvss" etc.
                }
            }

        Logic:
        ------
        1. Identify polymers that are out of scope and move them to OOS "POLYMER".
        2. If any polymer and bondable terms are found, move bondable to OOS "OTHERS".
        3. Special handling for "polyether" polymer (New requirement. Not in OOS list, currently hardcoded)
        4. Identify brands that are out of scope and move them to OOS "BRAND".
        5. Identify fillers that are out of scope and move them to OOS "FILLER". If no In-Scope fillers are found, set In-Scope FILLER to empty list.
        6. Identify grades that are out of scope and move them to OOS "GRADE".
        7. Check for color codes in grades and remove them from both In-Scope and OOS grades.
        8. Identify "OTHERS" out of scope items like "toyota", "fda", "amorphous", "fmvss" etc. and move them to OOS "OTHERS" based on pattern matching.
        """

        out_of_scope_output = {"active":False,"entities":{"GRADE": [], "BRAND": [], "POLYMER": [], "FILLER": [],"OTHERS":[]}}
        
        if result["POLYMER"]:
            out_of_scope_polymers_identified = [polymer_name for polymer_name in result["POLYMER"] if re.sub(r'[^a-zA-Z\d]', '', polymer_name) in DEPENDENCIES['OUT_OF_SCOPE_DATA']['polymers']]  
            if out_of_scope_polymers_identified:
                result["POLYMER"] = list(set(result["POLYMER"]) - set(out_of_scope_polymers_identified))
                out_of_scope_output["active"]=True
                out_of_scope_output["entities"]["POLYMER"] = out_of_scope_polymers_identified
        
        bonding_pattern = r'\b(bond[a-z]*(able|ing|ed)|adhesi(ve|on)|cohesi(ve|on))\b' 
        if result["POLYMER"] and re.search(bonding_pattern, search_query_cleaned):
            out_of_scope_output["active"]=True
            out_of_scope_output["entities"]["OTHERS"].append("bondable")
        if result["POLYMER"] and "polyether" in result["POLYMER"]:
            result["POLYMER"].remove("polyether")
            out_of_scope_output["active"]=True
            out_of_scope_output["entities"]["POLYMER"].append("polyether")
            out_of_scope_output["entities"]["POLYMER"] = list(set(out_of_scope_output["entities"]["POLYMER"]))
        
        # if result["BRAND"]:
        #     out_of_scope_brands_identified = [brand_name for brand_name in result["BRAND"] if brand_name in DEPENDENCIES['OUT_OF_SCOPE_DATA']['brands']]  
        #     if out_of_scope_brands_identified:
        #         result["BRAND"] = list(set(result["BRAND"]) - set(out_of_scope_brands_identified))
        #         out_of_scope_output["active"]=True
        #         out_of_scope_output["entities"]["BRAND"] = out_of_scope_brands_identified

        if result["BRAND"] == ['bexloy']:
            result["BRAND"] = ['hytrel']

        if result["BRAND"]:
            out_of_scope_brands_identified = []
            internal_brands = DEPENDENCIES['OUT_OF_SCOPE_DATA']['brands_internal']
            commercial_brands = DEPENDENCIES['OUT_OF_SCOPE_DATA']['brands_commerical']
            not_in_scope_brands = DEPENDENCIES['OUT_OF_SCOPE_DATA']['brands_not_in_scope']

            if user_type == "internal":
                for brand_name in result["BRAND"]:
                    if brand_name in internal_brands or brand_name in commercial_brands:
                        continue  
                    elif brand_name in not_in_scope_brands:
                        out_of_scope_brands_identified.append(brand_name)

            elif user_type == "external":
                for brand_name in result["BRAND"]:
                    if brand_name in commercial_brands or brand_name in not_in_scope_brands: #"""brand_name in internal_brands or """ 
                        out_of_scope_brands_identified.append(brand_name)

            result["BRAND"] = list(set(result["BRAND"]) - set(out_of_scope_brands_identified))
            out_of_scope_output["active"] = bool(out_of_scope_brands_identified)
            out_of_scope_output["entities"]["BRAND"] = out_of_scope_brands_identified



        if result["FILLER"]: 
            filler_info = result["FILLER"][0]  
            if 'filler_name' in filler_info.keys():
                out_of_scope_fillers_identified = [filler_name for filler_name in filler_info['filler_name'] if filler_name in DEPENDENCIES['OUT_OF_SCOPE_DATA']['fillers']]
                if out_of_scope_fillers_identified:
                    filler_info['filler_name'] = list(set(filler_info['filler_name']) - set(out_of_scope_fillers_identified))
                    out_of_scope_output["active"]=True
                    out_of_scope_output["entities"]["FILLER"] = out_of_scope_fillers_identified
                    if len(filler_info['filler_name'])==0:
                        result["FILLER"]=[]
        
        if result["GRADE"]:
            if user_type == "internal":
                all_grades_inscope = DEPENDENCIES['OUT_OF_SCOPE_DATA']['gradesInScope']
                all_grades_outofscope = DEPENDENCIES['OUT_OF_SCOPE_DATA']['grades']
            else:
                all_grades_inscope = DEPENDENCIES['OUT_OF_SCOPE_DATA']['gradesInScopeExternal']
                all_grades_outofscope = DEPENDENCIES['OUT_OF_SCOPE_DATA']['gradesExternal'] + DEPENDENCIES['OUT_OF_SCOPE_DATA']['gradesInScope']
            out_of_scope_grades_identified = []
            updated_grade_names = []
            for grade_name in result["GRADE"]:
                is_out_of_scope_grade_identified = False
                grade_name_normalized = re.sub(r'\W+', '', grade_name)
                if not any(grade_name_normalized in substring for substring in all_grades_inscope):   
                    if any(grade_name_normalized in substring for substring in all_grades_outofscope):
                       is_out_of_scope_grade_identified = True
                       out_of_scope_grades_identified.append(grade_name) 
                       continue;
                    #remove color code if present
                    grade_name_updated = re.sub(DEPENDENCIES["OOS_COLOR_CODE_PATTERN"], '', grade_name).rstrip()
                    grade_name_updated = re.sub(r"([-,/ ])(bk|black)$" , '', grade_name_updated)

                    if grade_name_updated=="":
                        continue;
                        
                    updated_grade_names.append(grade_name_updated)
                    grade_name_normalized = re.sub(r'\W+', '', grade_name_updated)
                    #check for out of scope grade match
                    if grade_name_normalized in all_grades_outofscope:
                        is_out_of_scope_grade_identified = True
                    elif any(grade_name_normalized in substring for substring in all_grades_outofscope):
                        is_out_of_scope_grade_identified = True
                    elif any(x.replace(" ", "") in grade_name_normalized for x in DEPENDENCIES['OUT_OF_SCOPE_DATA']['brands'] if len(x)>3):
                        is_out_of_scope_grade_identified = True
                    
                    #check if it is an actual grade after color code removal
                    if is_out_of_scope_grade_identified and not any(grade_name_normalized in substring for substring in all_grades_inscope):
                        out_of_scope_grades_identified.append(grade_name_updated)   
                    else:
                        is_out_of_scope_grade_identified = False
                else:
                    updated_grade_names.append(grade_name)
                    

            if out_of_scope_grades_identified:
                result["GRADE"] = list(set(updated_grade_names) - set(out_of_scope_grades_identified))
                out_of_scope_output["active"]=True
                out_of_scope_output["entities"]["GRADE"] = out_of_scope_grades_identified 
            else:
                result["GRADE"] = updated_grade_names
        
        # if result["FEATURE"] and 'chemical resistant' in result["FEATURE"]:
        #     result["FEATURE"].remove('chemical resistant')
        #     out_of_scope_output["active"]=True
        #     out_of_scope_output["entities"]["OTHERS"].append("chemical resistant")
        if result["AUTO_CERT"]:
            if any(item['oem'] == 'toyota' for item in result["AUTO_CERT"]):
                result["AUTO_CERT"] = [item for item in result["AUTO_CERT"] if item['oem'] != 'toyota'] 
                out_of_scope_output["active"]=True
                out_of_scope_output["entities"]["OTHERS"].append("toyota")
        elif "toyota" in search_query_cleaned:
            out_of_scope_output["active"]=True
            out_of_scope_output["entities"]["OTHERS"].append("toyota")
        
        fda_substrings = ['fda', 'food contact', 'food grade', 'food approval', 'food approved']
        if any(re.search(r'\b' + re.escape(substring) + r'\b', search_query_cleaned) for substring in fda_substrings):
            out_of_scope_output["active"]=True
            out_of_scope_output["entities"]["OTHERS"].append("fda")
        amorphous_strings = ['amorphous']
        if any(re.search(r'\b' + re.escape(substring) + r'\b', search_query_cleaned) for substring in amorphous_strings):
            out_of_scope_output["active"]=True
            out_of_scope_output["entities"]["OTHERS"].append("amorphous")
        fmvss_strings = ['fmvss']
        if any(re.search(r'\b' + re.escape(substring) + r'\b', search_query_cleaned) for substring in fmvss_strings):
            out_of_scope_output["active"]=True
            out_of_scope_output["entities"]["OTHERS"].append("fmvss")
        # carbon_strings = ['carbon footprint', 'iso 14067', 'iso14067', 'carbon capture and utilization', 'ccu', 'carbon capture']
        # if any(re.search(r'\b' + re.escape(substring) + r'\b', search_query_cleaned) for substring in carbon_strings):
        #     out_of_scope_output["active"]=True
        #     out_of_scope_output["entities"]["OTHERS"].append("carbon footprint")
        cfr_strings = ['cfr 21', 'cfr21','cfr-21']
        if any(re.search(r'\b' + re.escape(substring) + r'\b', search_query_cleaned) for substring in cfr_strings):
            out_of_scope_output["active"]=True
            out_of_scope_output["entities"]["OTHERS"].append("cfr 21")
        crosslinked_pattern = re.compile(r'cross\s*-?\s*link', re.IGNORECASE)
        if crosslinked_pattern.search(search_query_cleaned):
            out_of_scope_output["active"]=True
            out_of_scope_output["entities"]["OTHERS"].append("crosslinked")
        maf_strings = ['device master file', 'maf']
        if any(re.search(r'\b' + re.escape(substring) + r'\b', search_query_cleaned) for substring in maf_strings):
            out_of_scope_output["active"]=True
            out_of_scope_output["entities"]["OTHERS"].append("device master file")
        dmf_strings = ['drug master file', 'dmf']
        if any(re.search(r'\b' + re.escape(substring) + r'\b', search_query_cleaned) for substring in dmf_strings):
            out_of_scope_output["active"]=True
            out_of_scope_output["entities"]["OTHERS"].append("drug master file")
        iso10993_strings = ['iso 10993', 'iso10993']
        if any(re.search(r'\b' + re.escape(substring) + r'\b', search_query_cleaned) for substring in iso10993_strings):
            out_of_scope_output["active"]=True
            out_of_scope_output["entities"]["OTHERS"].append("iso 10993")
        ltha_pattern = re.compile(r'(?<!\w)ltha(?!\w)|long\s*-?\s*term\s*-?\s*heat\s*-?\s*aging')  
        if ltha_pattern.search(search_query_cleaned): 
            out_of_scope_output["active"]=True
            out_of_scope_output["entities"]["OTHERS"].append("long term heat aging")
        usp_pattern = re.compile(r'(?<!\w)usp(?!\w)|usp\s*-?\s*23|usp\s*-?\s*88') 
        if usp_pattern.search(search_query_cleaned):
            out_of_scope_output["active"]=True
            out_of_scope_output["entities"]["OTHERS"].append("usp")
        addictive_strings = ['addictive','addictives']
        if any(re.search(r'\b' + re.escape(substring) + r'\b', search_query_cleaned) for substring in addictive_strings):
            out_of_scope_output["active"]=True
            out_of_scope_output["entities"]["OTHERS"].append("addictives")
                

        return out_of_scope_output
