import os
import logging
import traceback
import json
import pandas as pd
# from spello.model import SpellCorrectionModel
import re
from ner_helper import run_ner


def init():
    """
    Initializes the global variables and loads necessary data files for the scoring module.
    
    This function serves as the initialization point when the container starts up. It performs
    the following key tasks:
    1. Sets up global configuration variables for model versioning and API
    2. Loads various data files needed for processing, including:
       - Unit conversion tables (general and exceptions)
       - Unique values and grade names
       - Normalized values for grade mapping
       - Normalized competitor names
       - Out of scope data
       - Color code data
       - UL list name values
    
    Parameters:
        None
        
    Returns:
        None
        
    Flow:
    - Determines the base path for model files using AZUREML_MODEL_DIR environment variable
    - Sets up GPT deployment configurations for different environments
    - Loads multiple CSV and JSON files containing reference data into global variables
    
    Global Variables Set:
    - UNIQUE_VALUES: Dictionary of unique reference values
    - MODEL_VERSION: Version identifier for the model
    - API_VERSION: Version identifier for the API
    - DEPENDENCIES: Required dependencies for the model

    Note:
    - This function is called when the container is initialized/started, typically after create/update of the deployment.
    - You can write the logic here to perform init operations like caching the model in memory
    """

    global UNIQUE_VALUES
    global MODEL_VERSION
    global API_VERSION
    global DEPENDENCIES
    
    # AZUREML_MODEL_DIR is an environment variable created during deployment.
    # It is the path to the model folder (./azureml-models/$MODEL_NAME/$VERSION)
    if "AZUREML_MODEL_DIR" in os.environ:
        base_path = os.getenv("AZUREML_MODEL_DIR")
    else:
        # local
        base_path = "././"
    
    # Define GPT deployment to use
    ENVIRONMENT = "NPROD" #"PROD"
    #GPT_DEPLOYMENT_NPROD = "oai-gpt-4-1-mini-NER-2025-06-16-gst-d-usnc-01"
    # GPT_DEPLOYMENT_NPROD = "oai-gpt-4-1-mini-NER-2025-08-05-gst-d-usnc-01"
    # GPT_DEPLOYMENT_NPROD = "aif-gpt-4-1-mini-NER-2026-04-17-aif-gst-ussc-01"
    GPT_DEPLOYMENT_NPROD = "aif-gpt-4-1-mini-NER-2026-07-15-aif-gst-ussc-01" #latest deployment
    #GPT_DEPLOYMENT_PROD = "oai-gpt-4o-mini-NER-2025-06-16-gst-d-usnc-01-prod"
    GPT_DEPLOYMENT_PROD = "aif-gpt-4-1-mini-NER-2026-05-11-aif-gst-ussc-01-prod"
    GPT_PROMPT = "Act as an NER model trained on the data corpus of 'Celanese' which is a global chemical leader in the production of differentiated chemistry solutions and specialty materials used in most major industries and consumer applications. Ensure the output is a structured dictionary format."


    unit_conversion_table_path = os.path.join(base_path, "dependencies/final_unit_conversion_table.csv")
    UNIT_CONVERSION_TABLE_GENERAL = pd.read_csv(unit_conversion_table_path)
    
    unit_conversion_table_for_exeptions_path = os.path.join(base_path, "dependencies/final_unit_conversion_table_for_exeptions.csv")
    UNIT_CONVERSION_TABLE_FOR_EXEPTIONS = pd.read_csv(unit_conversion_table_for_exeptions_path)

    unique_values_file_path = os.path.join(base_path, "dependencies/unique_values_22_02_24.json")
    with open(file=unique_values_file_path) as f:
        UNIQUE_VALUES = json.load(f)
    GRADE_NAMES = UNIQUE_VALUES['GRADE']

    normalized_unique_values_file_path = os.path.join(base_path, "dependencies/normalized_unique_values_for_grade_mapping.json")
    with open(file=normalized_unique_values_file_path) as f:
        NORMALIZED_UNIQUE_VALUES = json.load(f)
    
    normalized_competitor_names_file_path = os.path.join(base_path, "dependencies/normalized_competitor_names.json")
    with open(file=normalized_competitor_names_file_path) as f:
        NORMALIZED_COMPETITOR_NAMES = json.load(f)

    outOfScopeData_file_path = os.path.join(base_path, "dependencies/outOfScopeData.json")
    with open(file=outOfScopeData_file_path) as f:
        OUT_OF_SCOPE_DATA = json.load(f)

    OOS_Color_code_pattern_file_path = os.path.join(base_path, "dependencies/oos_color_code_pattern.txt")
    with open(file=OOS_Color_code_pattern_file_path, encoding='latin-1') as f:
        OOS_COLOR_CODE_PATTERN = f.read()

    ul_list_name_value_path = os.path.join(base_path, "dependencies/ul_list_name_value.json")
    with open(file=ul_list_name_value_path) as f:
        UL_LIST_NAME_VALUE = json.load(f)

    
    df_abb_prp = pd.read_excel(
        os.path.join(base_path, "dependencies/abbreviations.xlsx"), sheet_name='PROPERTY')
    df_abb_filler = pd.read_excel(
        os.path.join(base_path, "dependencies/abbreviations.xlsx"), sheet_name='FILLER')
    df_abb_ft = pd.read_excel(
        os.path.join(base_path, "dependencies/abbreviations.xlsx"), sheet_name='FEATURE')
    df_abb_common = pd.read_excel(
        os.path.join(base_path, "dependencies/abbreviations.xlsx"), sheet_name='common_abb')
    df_abb_prp = df_abb_prp.apply(lambda x: x.astype(str).str.lower())
    df_abb_filler = df_abb_filler.apply(lambda x: x.astype(str).str.lower())
    df_abb_ft = df_abb_ft.apply(lambda x: x.astype(str).str.lower())
    df_abb_common = df_abb_common.apply(lambda x: x.astype(str).str.lower())

    property_abb = list(df_abb_prp.sort_values(
        'Abbreviations', key=lambda x: x.str.len(), ascending=False).to_records(index=False))
    filler_abb = list(df_abb_filler.sort_values(
        'Abbreviations', key=lambda x: x.str.len(), ascending=False).to_records(index=False))
    feature_abb = list(df_abb_ft.sort_values(
        'Abbreviations', key=lambda x: x.str.len(), ascending=False).to_records(index=False))

    ABBREVIATIONS = {'PROPERTY': property_abb,
                     'FILLER': filler_abb, 'FEATURE': feature_abb, 'common_abb': df_abb_common['WORDS']}

    FILTERED_VALUES, UNITS_LIST = get_filtered_values()

    ul_terms = get_ul_terms()
    ul_terms += list(UL_LIST_NAME_VALUE.keys())

    for ulp in UL_LIST_NAME_VALUE:
        ul_terms += UL_LIST_NAME_VALUE[ulp]['synonyms']
        ul_terms += UL_LIST_NAME_VALUE[ulp]['values']

    UL_TERMS = list(set(ul_terms))
          

    # MODEL_VERSION = "GPT4-1-mini-06_16_25"
    # MODEL_VERSION = "GPT-4-1-mini-08_05_25"
    # MODEL_VERSION = "GPT-4-1-mini-17_04_26"
    MODEL_VERSION = "GPT-4-1-mini-15_07_26"
    API_VERSION = "v5.9.2"

    DEPENDENCIES = {
        "ENVIRONMENT":ENVIRONMENT,
        "GPT_DEPLOYMENT_NPROD":GPT_DEPLOYMENT_NPROD,
        "GPT_DEPLOYMENT_PROD":GPT_DEPLOYMENT_PROD,
        "GPT_PROMPT":GPT_PROMPT,
        "UNIQUE_VALUES":UNIQUE_VALUES,
        "UNIT_CONVERSION_TABLE_GENERAL":UNIT_CONVERSION_TABLE_GENERAL,
        "UNIT_CONVERSION_TABLE_FOR_EXEPTIONS":UNIT_CONVERSION_TABLE_FOR_EXEPTIONS,
        "GRADE_NAMES":GRADE_NAMES,
        "ABBREVIATIONS":ABBREVIATIONS,
        "FILTERED_VALUES":FILTERED_VALUES,
        "UNITS_LIST":UNITS_LIST,
        "NORMALIZED_UNIQUE_VALUES":NORMALIZED_UNIQUE_VALUES,
        "NORMALIZED_COMPETITOR_NAMES":NORMALIZED_COMPETITOR_NAMES,
        "OUT_OF_SCOPE_DATA":OUT_OF_SCOPE_DATA,
        "OOS_COLOR_CODE_PATTERN":OOS_COLOR_CODE_PATTERN,
        "UL_LIST_NAME_VALUE": UL_LIST_NAME_VALUE,
        "UL_TERMS": UL_TERMS,
        "MODEL_VERSION":MODEL_VERSION,
        "API_VERSION":API_VERSION}

    logging.info("Init complete")

def get_filtered_values() -> list:
    """
    Extracts and processes special values and units from UNIQUE_VALUES dictionary.

    This function serves two main purposes:
    1. Identifies and extracts words containing special characters (., -, /) from UNIQUE_VALUES
    2. Maintains a comprehensive list of measurement units

    Algorithm:
    1. Iterates through UNIQUE_VALUES dictionary
    2. Splits each value into words
    3. Filters words containing special characters (., -, /)
    4. Maintains separate lists for all filtered values and units
    5. Adds predefined unit measurements to units list
    6. Deduplicates filtered values list

    Parameters:
        None - Uses global UNIQUE_VALUES dictionary

    Returns:
        tuple: Contains two lists:
            - filtered_values (list): Deduplicated list of all values containing special characters and units
            - units_list (list): List of measurement units including both extracted and predefined units
    """

    filtered_values = []
    units_list = []
    for k in UNIQUE_VALUES:
        for value in UNIQUE_VALUES[k]:
            words = value.split()
            for word in words:
                if (re.search("\.", word) or re.search("-", word) or re.search("/", word)) and (word not in ["-", "/", "."]):
                    filtered_values.append(word)
                    if k == "UNIT":
                        units_list.append(word)
    units_list += ["g/ml", "w/m.k", "kg/m^3", "g/cm^3", "kj/m^2", "g/cm^3", "grams/cm^2", "g/cc", "ohm/m",
                   "kj/m^3", "g/cc", "kg/m3", "kn/m", "kv/mm", "kg/m3", "g/cm3", "j/m^2", "kg/cc", "kn/m", "w/m.k"]
    filtered_values = list(set(filtered_values + units_list))
    return filtered_values, units_list


def get_ul_terms():
    """
    Retrieves a comprehensive list of UL (Underwriters Laboratories) related terms and their variations used in Celanese.

    This function maintains a static list of standardized UL terminology, including:
    - UL Properties
    - UL Sub-Properties

    The function serves to:
    1. Provide a standardized vocabulary for UL-related material properties
    2. Support pattern matching and synonym mapping.

    Parameters:
        None

    Returns:
        list: A comprehensive list of lowercase UL-related terms and their variations,
              including official terminology and common industry synonyms

    Note:
    - The list was used in older version of the NER model and is not used in the current version.
    """

    ul_terms = [
        "comparative tracking", "comparative tracking index", "cti", 'comparative tracking index rating', 
        'comparative tracking rating', "v0", "v1", "v2", "v-0", "v-1", "v-2", "v 0", "v 1", "v 2", "hb", "5va", "5vb", "vh2",
        'flame class', 'flammability', 'flame rating', "high current arc", "high current arc ignition", "high arc ignition", 
        "arc ignition", "high ampere arc ignition", "high amp arc ignition", "HAI", "high amp", "hot wire ignition", "HWI", "hot wire",
        "rti", "relative thermal index", "relative thermal index electrical", "rti-e", "rti elec", "rti electrical", 
        "relative thermal index mechanical impact", "relative thermal index impact", "rti-i", "rti imp", "rti impact",
        "relative thermal index mechanical strength", "relative thermal index strength", "rti-s", "rti str", "rti strength",
        "ul temp", "ul temperature", "ul94", "ulg", "ulh", "ul",
        # new terms
        "thickness","min thickness","min. thickness","minimum thickness", "min thk", "minimum thk",
        'ul listing', 'ul', 'ul94', 'ulv0', 'ul94v', 'ul746c', 'ul746', 
        'arc resistance', 'arc resistance performance level category', 'arc resist performance level category', 'hvar', 'arc resistivity performance level category', 'high voltage arc resist to ignition', 'high voltage arc resistant to ignition', 'high voltage arc resistance to ignition', 'high voltage arc resistivity to ignition', 'arc resistant performance level category', 
        'ball pressure test', 'resist to heat', 'resis to heat', 'ball pressure', 'resistance to heat', 'resistant to heat', 
        'comparative tracking index', 'tracking resist', 'tracking resistivity', 'tracking resistance', 'tracking resistant', 'cti', 'comparative tracking index', 'comparative tracking index cti', 'iec tracking index', 'comparative tracking index', 
        'dielectric strength', 'electric strength', 'electrical strength', 'electristrength', 'ac electristrength', 'dc electristrength', 'dc dielectric strength', 'dielectric strength', 'ac', 'elstr-temp', 'dc', 'ac dielectric strength', 
        'dimensional change', 'dim change', 
        'flammability classification', 'flame class', 'flame classification', 'flammability', 'burning behavior ul 94', 'ul94', 'flammability ul 94', 'ul94 rating', 'burning behav.', 
        'glow wire flammability index', 'glow-wire flammability', 'gwfi', 'glow wire flammability', 'glow-wire flammability index', 'glow wire test', 
        'glow wire ignition temperature', 'glow wire ignition', 'glow wire test', 'gwit', 'glow wire temperature', 'glow wire temp', 'glow-wire ignition temperature', 'glow wire', 
        'high voltage arc tracking rate (hvtr)', 'hvtr', 'high voltage arc tracking rate', 'high vol arc tracking rate', 'high voltagetracking rate', 'high voltage arc tracking', 
        'high-current arc ignition (hai)', 'high-current arc ignition', 'high amp arc ignition', 'high ampere arc ignition', 'high amperage arc ignition category', 'hai', 
        'hot wire ignition (hwi)', 'hot wire ignition', 'hwi', 'hot-wire ignition', 
        'inclined-plane tracking', 'ip tracking', 'ipt', 'inclined plane', 'plane tracking', 
        'non-halogenated material', 'nhm', 'non halo material', 
        'outdoor suitability', 'f1', 'f2', 'outdoor durability', 'durability', 
        'detergent resistant', 'detergent resist', 'detergent resistivity', 'detergent resis', 'detergent res', 'deterres', 'f3', 'f4', 'f 3', 'f 4',
        'rohs 2011/65/eu material', 'rohs material', '2011/65/eu material', '2011/65/eu'
    ]
    
    ul_terms = [x.lower() for x in ul_terms]
    return ul_terms


def run(raw_data):
    """
    This function is called for every invocation of the endpoint to perform the actual scoring/prediction.

    Main entry point for the NER (Named Entity Recognition) scoring endpoint. Processes raw input data 
    containing search queries and returns structured entity recognition results.

    Parameters:
        raw_data (str): A JSON-formatted string containing the input data. Expected to have a "data" 
                       field containing the search query text to be processed.

    Returns:
        dict: A structured dictionary containing the NER results with the following key components:
            - userInput: Contains the original search query
            - modelOutput: 
                - entities: Contains the extracted entities (16 like GRADE, APPLICATION, etc.) by the pre-processing / NER Model.
                - unidentified: Contains the search query that is junk / non-searchable.
                - outOfScope: Contains the text that was identified as out of scope
            - modelVersion: Version of the NER model used
            - apiVersion: Version of the API
            
            If an error occurs during processing, returns a default structure with empty entity lists.

    Logic:
        1. Parses the JSON input to extract the search query
        2. Calls run_ner() to perform Named Entity Recognition on the query
        3. If an exception occurs during processing, catches it and returns a default response structure
        4. Logs the start and completion of request processing
    """
    
    logging.info("Request received")
    raw_data = json.loads(raw_data)
    search_query = raw_data["data"]
    if "user_type" in raw_data and isinstance(raw_data["user_type"], str) and raw_data["user_type"].lower() == "internal":
        user_type = raw_data["user_type"].lower()
    else:
        user_type = "external"
    logging.info("input: "+str(search_query))

    
    try:
        ner_output = run_ner(search_query, DEPENDENCIES, user_type)
    except Exception as e:
        print(e)
        print(traceback.format_exc())
        print("EXCEPTION ERROR for: ", search_query)
        ner_output = {
            "userInput": {
                "searchQuery": search_query
            },
            "modelOutput": {
                "entities": {
                        "GRADE": [],
                        "APPLICATION": [],
                        "BRAND": [],
                        "POLYMER": [],
                        "PROPERTY": [],
                        "FILLER": [],
                        "FEATURE": [],
                        "PROCESSING": [],
                        "DELIVERY_FORM": [],
                        "COMPETITOR_GRADE": [],
                        "AUTO_CERT": [],
                        "RAILWAY_CERT": [],
                        "WATER_CERT": [],
                        "NSF_CERT": [],
                        "INDUSTRY": [],
                        "REGION": [],
                        "MATERIAL_ID": []},
                "unidentified": search_query,
                "outOfScope": {
                    "active": False,
                    "entities": {"GRADE": [],
                        "BRAND": [],
                        "POLYMER": [],
                        "FILLER": [],
                        "OTHERS": []}}
            },
            "modelVersion": MODEL_VERSION,
            "apiVersion": API_VERSION
        }
    logging.info("Request processed")
    return ner_output

# local testing
# if __name__ == '__main__' :
#     init()
#     ner_output = run('{"data": "looking for a selar grade which is dermal irritaion free", "user_type":"internal"}')

#     print("#"*50, ner_output)

    # ner_output = run('{"data": "pvdf alternatives"}')
    # ner_output = run('{"data": "celanex 1602Z"}')
    # ner_output = run('{"data": "Laser Markable, Glass fiber: 25, Flammability Classification: V-0, Minimum Thickness: 0.8 mm, Glow Wire Flammability Index: greater than 850°C, Relative Thermal Index -: 140, Non-halogenated/Red phosphorous free flame retardant", "user_type":"internal"}')
    # ner_output = run('{"data": "30% glass filled UV resistant nylon 66 with UL94V0", "user_type":"internal"}')
    # ner_output = run('{"data": "eva"}')
    # ner_output = run('{"data": "ST8018 natural"}')
    # ner_output = run('{"data": "STP121-62M100LD3003 BLK "}')
    # ner_output = run('{"data": "Tecnoprene TCFK6TILE YI "}')
    # ner_output = run('{"data": "POM NW-02"}')
    # ner_output = run('{"data": "at 4200"}')
    # ner_output = run('{"data": "Celanyl B3 j05 GFB2020 BK 9005"}') # CelanylB3j05GFB is in the OOS list but not CelanylB3j05GFB2020
    # ner_output = run('{"data": "IMDS 121-73W175"}')
    # ner_output = run('{"data": "duracon"}')
    # ner_output = run('{"data": "water absorption 2mm minimum 2%"}')
    # ner_output = run('{"data": "connector for switch"}')
    # ner_output = run('{"data": "grade for using in medical bed and another one for connector for car"}')
    # ner_output = run('{"data": "grade for using in medical bed and another one for connector for switch"}')
    # ner_output = run('{"data": "grade for using in busbar in automotive and another one for connector for car"}')

    # ner_output = run('{"data": "8500bs"}')
    # ner_output = run('{"data": "lfrt grade"}')
    # ner_output = run('{"data": "pbt-gf30"}')
    # ner_output = run('{"data": "im looking for a pbt-gf"}')
    # ner_output = run('{"data": "Offset to 300CP"}')
    # ner_output = run('{"data": "celcon uv90"}')
    # ner_output = run('{"data": "pa 66, gf10"}')
    # ner_output = run('{"data": "celcon m90 ecob"}')
    # ner_output = run('{"data": "i am looking for an ecob grade"}')
    # ner_output = run('{"data": "pp-lgf30 for ip"}')
    # print(ner_output)
    # ner_output = run('{"data": "lfrt grade"}')
    # ner_output = run('{"data": "pbt-gf30"}')
    # ner_output = run('{"data": "im looking for a pbt-gf"}')
    # ner_output = run('{"data": "Offset to 300CP"}')
    # ner_output = run('{"data": "celcon uv90"}')
    # ner_output = run('{"data": "pa 66, gf10"}')
    # ner_output = run('{"data": "gwit≥775C"}')
    # ner_output = run('{"data": "CELANEX 1602Z", "user_type":""}')
    # ner_output = run('{"data": "fortron fx32t1", "user_type":"internal"}')
    # ner_output = run('{"data": "tensile modulus of 100", "user_type":""}')
    # ner_output = run('{"data": "tensile modulus tape 34gpa"}')
    # ner_output = run('{"data": "Celanex® 2302 GV1/30 ECO-R", "user_type":""}')
