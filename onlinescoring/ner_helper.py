import time
import pandas as pd
# from pathlib import Path
from thefuzz import fuzz
from thefuzz import process as process
#from fuzzmatch import FuzzMatcher
#from rapidfuzz import fuzz as rfuzz
#from rapidfuzz import process as rprocess
import copy
import re
import os
from openai import AzureOpenAI
from dotenv import load_dotenv, find_dotenv
_ = load_dotenv(find_dotenv()) 

azure_openai_key = os.getenv('azure_openai_key_aif')
azure_openai_endpoint = os.getenv('azure_openai_endpoint_aif')
api_version = os.getenv('api_version_aif')
client = AzureOpenAI(
    api_key=azure_openai_key,
    api_version=api_version,
    azure_endpoint=azure_openai_endpoint,
   
)

# from pre_processing import trim
from post_processing import modifier_unit_conversion, validate_medical_cert_values, validate_result_dict, identify_out_of_scope_items, validate_chemical_resistance_values, reclassify_feature_to_chem_res, validate_feature_for_med_cert
from pre_processing import data_preprocessing, GRADE_OFFSET_TERMS

def replace_sublist(main_list, sublist, new_sublist):
    """
    Replaces all occurrences of a specified sublist in the main list with a new sublist.

    Parameters:
    main_list (list): The list in which the sublist will be searched and replaced.
    sublist (list): The sublist to be found and replaced within the main list.
    new_sublist (list): The new sublist that will replace the found sublist.

    Returns:
    list: A new list with all occurrences of the sublist replaced by the new sublist.
          If the sublist is not found or if the function runs into issues, the original list is returned.

    Notes:
    - The function only replaces exact matches of the sublist.
    - The function ensures that no infinite loop occurs by limiting the number of iterations using `max_iterations`.
    - If either `sublist` or `new_sublist` is empty, no changes are made.
    - The function handles edge cases where the sublist is not found or the main list is empty.

    Example:
    Input: replace_sublist([1, 2, 3, 4, 5], [3, 4], [30, 40])
    Output: [1, 2, 30, 40, 5]
    """

    main_list_new = main_list.copy()
    main_len = len(main_list)
    sub_len = len(sublist)
    new_len = len(new_sublist)
    max_iterations = main_len + sub_len

    counter = 0
    if main_list_new and sublist and new_sublist:
        i = 0

        while i <= main_len - sub_len and counter < max_iterations:
            if main_list_new[i:i + sub_len] == sublist:
                main_list_new[i:i + sub_len] = new_sublist
                main_len = main_len - sub_len + new_len
                i += new_len
            else:
                i += 1
            counter += 1

    if counter >= max_iterations:
        main_list_new = main_list

    return main_list_new

def is_sublist(main_list, sublist) -> bool:
    """
    Checks if a sublist is present in a main list.

    Parameters:
    main_list (list): The list in which the sublist will be searched.
    sublist (list): The sublist to be found within the main list.

    Returns:
    bool: True if the sublist is found in the main list, False otherwise.
    """

    main_len = len(main_list)
    sub_len = len(sublist)
    for i in range(main_len - sub_len + 1):
        if main_list[i:i + sub_len] == sublist:
            return True

    return False

def clean_for_split(text: str):
    """
    Cleans a text string by replacing specific characters ('(', ')', '-', '.', ',') with spaces.

    Parameters:
    text (str): The text string to be cleaned.

    Returns:
    str: The cleaned text string with specified characters replaced by spaces.
    """

    return text.replace("(", " ").replace(")", " ").replace("-", " ").replace(".", "").replace(",", " ")

def is_word_found(word: str, text: str):
    """
    Checks if a specific word is present in a text string.

    Parameters:
    word (str): The word to search for within the text.
    text (str): The text string in which the word will be searched.

    Returns:
    bool: True if the word is found in the text, False otherwise.
    """

    word_found = False
    for i in [" ", "-", "/", "=", ".", ',']:
        words_list = [x.strip() for x in text.split(i)]
        if word == "lgf":
            if any(substring.startswith(word) for substring in words_list):
                word_found = True
                break
        else:
            if word in words_list:
                word_found = True
                break 
    return word_found

def replace_abbreviation(entities, abbreviations, sq):
    """
    Replaces abbreviations in the entities list with their full forms.

    Parameters:
    entities (dict): The dictionary containing the entities to be processed.
    abbreviations (dict): The dictionary containing the abbreviations and their meanings.
    sq (str): The search query string.

    Returns:
    dict: The updated entities dictionary with abbreviations replaced.

    Note:
    - The function handles the replacement of abbreviations for property, filler, and feature names.
    - It was used in previous version of the NER Model but the latest version of the model does not need this.
    """

    all_prop_meanings = [i[0] for i in abbreviations['PROPERTY']]
    all_filler_meanings = [i[0] for i in abbreviations['FILLER']]
    all_feature_meanings = [i[0] for i in abbreviations['FEATURE']]
    common_abb = abbreviations['common_abb']

    for p in entities['PROPERTY']:
        prop_found = False
        skip_prop = False
        full_match = False
        property_name = p['property_name']

        prop_words = property_name.split()
        prop_words2 = re.sub(r"[^a-zA-Z0-9 ]", " ", property_name).split()

        property_name2 = re.sub(r"[^a-zA-Z0-9 ]", " ", property_name)
        for meaning in all_prop_meanings:
            meaning2 = re.sub(r"[^a-zA-Z0-9 ]", " ", meaning)
            if (meaning in property_name) or (meaning2 in property_name2):
                skip_prop = True
        
        if skip_prop:
            continue
        
        if any(c_abb in property_name.split() for c_abb in common_abb) \
            or any(c_abb in property_name2.split() for c_abb in common_abb):
            full_match = True

        for abb_prop in abbreviations['PROPERTY']:
            abb_prop_words = abb_prop[1].split()
            abb_prop_full_words = abb_prop[0].split()
            abb_prop_full_words2 = re.sub(r"[^a-zA-Z0-9 ]", " ", abb_prop[0]).split()
            if is_sublist(prop_words, abb_prop_words) and not prop_found and not is_sublist(prop_words, abb_prop_full_words) \
                and not is_sublist(prop_words2, abb_prop_full_words2) and not full_match:
                if abb_prop[1] == "tm" and "pa" in p['modifier']['unit']:
                    p['property_name'] = "tensile modulus"
                    prop_found = True
                    break
                property_name_words = replace_sublist(
                    prop_words, abb_prop_words, abb_prop[0].split())
                p['property_name'] = ' '.join(property_name_words)
                prop_found = True
                break

            elif property_name == abb_prop[1] or property_name2 == abb_prop[1]:
                if abb_prop[1] == "tm" and "pa" in p['modifier']['unit']:
                    p['property_name'] = "tensile modulus"
                    prop_found = True
                    break
    
                p['property_name'] = abb_prop[0]
                prop_found = True
                break

    lft_found = is_word_found('lft', sq)
    lfrt_found = is_word_found('lfrt', sq)
    tp_found = is_word_found('tp', sq)
    lgf_found = is_word_found('lgf', sq)
    celstran_found = is_word_found('celstran', sq)
    if not celstran_found and not lft_found and not lfrt_found and tp_found:
        tp_found = False

    for f in entities['FILLER']:
        f_found = False
        skip_filler = False
        full_match = False
        filler_name = f['filler_name']

        filler_words = filler_name.split()
        filler_words2 = re.sub(r"[^a-zA-Z0-9 ]", " ", filler_name).split()

        filler_name2 = re.sub(r"[^a-zA-Z0-9 ]", " ", filler_name)
        for meaning in all_filler_meanings:
            meaning2 = re.sub(r"[^a-zA-Z0-9 ]", " ", meaning)
            if (meaning in filler_name) or (meaning2 in filler_name2):
                skip_filler = True

        if skip_filler:
            continue

        if any(c_abb in filler_name.split() for c_abb in common_abb) \
            or any(c_abb in filler_name2.split() for c_abb in common_abb):
            full_match = True

        for abb_filler in abbreviations['FILLER']:
            abb_filler_words = abb_filler[1].split()
            abb_filler_full_words = abb_filler[0].split()
            abb_filler_full_words2 = re.sub(r"[^a-zA-Z0-9 ]", " ", abb_filler[0]).split()
            if is_sublist(filler_words, abb_filler_words) and not f_found and not is_sublist(filler_words, abb_filler_full_words) \
                and not is_sublist(filler_words2, abb_filler_full_words2) and not full_match:
                filler_name_words = replace_sublist(
                    filler_words, abb_filler_words, abb_filler[0].split())
                f['filler_name'] = ' '.join(filler_name_words)

                if entities['BRAND'] and f['filler_name'] == "glass fiber":
                    for brand_name in entities['BRAND']:
                        if "celstran" in brand_name and not tp_found:
                            f['filler_name'] = "long glass fiber"
                
                if tp_found and f['filler_name'] == "glass fiber":
                    f['filler_name'] = "long glass fiber" # long glass continuous
                elif (lft_found or lfrt_found) and f['filler_name'] == "glass fiber":
                    f['filler_name'] = "long glass fiber"

                f_found = True
                break

            elif filler_name == abb_filler[1] or filler_name2 == abb_filler[1]:
                f['filler_name'] = abb_filler[0]

                if entities['BRAND'] and f['filler_name'] == "glass fiber":
                    for brand_name in entities['BRAND']:
                        if "celstran" in brand_name and not tp_found:
                            f['filler_name'] = "long glass fiber"
                
                if tp_found and f['filler_name'] == "glass fiber":
                    f['filler_name'] = "long glass fiber" # long glass continuous
                elif (lft_found or lfrt_found) and f['filler_name'] == "glass fiber":
                    f['filler_name'] = "long glass fiber"

                f_found = True
                break

    count = 0
    remove_fillers = []
    for i in entities['FILLER']:
        if i['filler_name'] in ['lft', 'lfrt', 'tp']:
            i['filler_percentage'] = 'unknown'
            count += 1
            remove_fillers.append(i)
        # elif i['filler_name'] == "lgf":
        #     i['filler_name']="glass fiber"
        #     i['filler_percentage'] = 'unknown'
            # count += 1
            # remove_fillers.append(i)
    
    extra_fillers = []
    # if ((lft_found or lfrt_found) and not entities['FILLER']) or (entities['FILLER'] and count == len(entities['FILLER'])):
    if (lft_found or lfrt_found or lgf_found):
        entities['BRAND'].append('celstran')
        for i in remove_fillers:
            entities['FILLER'].remove(i)
    elif entities['FILLER'] and count != len(entities['FILLER']):
        filler_names = [i['filler_name'] for i in entities['FILLER']]
        if lft_found and 'lft' not in filler_names:
            extra_fillers.append({'filler_name': 'lft', 'filler_percentage': 'unknown'})

        if lfrt_found and 'lfrt' not in filler_names:
            extra_fillers.append({'filler_name': 'lfrt', 'filler_percentage': 'unknown'})

        # tp to be treated as feature
        # if tp_found and 'tp' not in filler_names:
        #     extra_fillers.append({'filler_name': 'tp', 'filler_percentage': 'unknown'})

    if extra_fillers:
        entities['FILLER'].extend(extra_fillers)


    feature_names = []
    for feature_name in entities['FEATURE']:
        ft_found = False
        skip_feature = False
        full_match = False
        feature_name_new = ''
        feature_words = feature_name.split()
        feature_words2 = re.sub(r"[^a-zA-Z0-9 ]", " ", feature_name).split()

        feature_name2 = re.sub(r"[^a-zA-Z0-9 ]", " ", feature_name)
        for meaning in all_feature_meanings:
            meaning2 = re.sub(r"[^a-zA-Z0-9 ]", " ", meaning)
            if (meaning in feature_name) or (meaning2 in feature_name2):
                skip_feature = True

        if skip_feature:
            feature_names.append(feature_name)
            continue

        if any(c_abb in feature_name.split() for c_abb in common_abb) \
            or any(c_abb in feature_name2.split() for c_abb in common_abb):
            full_match = True

        for abb_feature in abbreviations['FEATURE']:
            abb_feature_words = abb_feature[1].split()
            abb_feature_full_words = abb_feature[0].split()
            abb_feature_full_words2 = re.sub(r"[^a-zA-Z0-9 ]", " ", abb_feature[0]).split()
            if is_sublist(feature_words, abb_feature_words) and not ft_found and not is_sublist(feature_words, abb_feature_full_words) \
                and not is_sublist(feature_words2, abb_feature_full_words2) and not full_match:
                feature_name_words = replace_sublist(
                    feature_words, abb_feature_words, abb_feature[0].split())
                feature_name_new = ' '.join(feature_name_words)
                ft_found = True
                break

            elif feature_name == abb_feature[1] or feature_name2 == abb_feature[1]:
                feature_name_new = abb_feature[0]
                ft_found = True
                break

        if ft_found:
            feature_names.append(feature_name_new)
        else:
            feature_names.append(feature_name)

    entities['FEATURE'] = feature_names

    return entities

def cti_value_convertion(value):
    """
    Converts a given value to a corresponding PLC (Performance Level Category) value for the UL property 'Comparative Tracking Index'.

    Parameters:
    value (int): The value to be converted to a PLC value.

    Returns:
    str: The PLC value as a string.
    """

    if value >= 600:
        return "plc 0"
    elif value >= 400:
        return "plc 1"
    elif value >= 250:
        return "plc 2"
    elif value >= 175:
        return "plc 3"
    elif value >= 100:
        return "plc 4"
    else:
        return "plc 5"
    
def hai_value_convertion(value):
    """
    Converts a given value to a corresponding PLC (Performance Level Category) value for the UL property 'High-Current Arc Ignition'.

    Parameters:
    value (int): The value to be converted to a PLC value.

    Returns:
    str: The PLC value as a string.
    """

    if value >= 120:
        return "plc 0"
    elif value >= 60:
        return "plc 1"
    elif value >= 30:
        return "plc 2"
    elif value >= 15:
        return "plc 3"
    else:
        return "plc 4"
    
def hwi_value_convertion(value):
    """
    Converts a given value to a corresponding PLC (Performance Level Category) value for the UL property 'Hot Wire Ignition'.

    Parameters:
    value (int): The value to be converted to a PLC value.

    Returns:
    str: The PLC value as a string.
    """

    if value >= 120:
        return "plc 0"
    elif value >= 60:
        return "plc 1"
    elif value >= 30:
        return "plc 2"
    elif value >= 15:
        return "plc 3"
    elif value >= 7:
        return "plc 4"
    else:
        return "plc 5"
    
def hvar_value_convertion(value):
    """
    Converts a given value to a corresponding PLC (Performance Level Category) value for the UL property 'High-Voltage Arc Ignition'.

    Parameters:
    value (int): The value to be converted to a PLC value.

    Returns:
    str: The PLC value as a string.
    """

    if value >= 300:
        return "plc 0"
    elif value >= 120:
        return "plc 1"
    elif value >= 30:
        return "plc 2"
    else:
        return "plc 3"
    
def hvtr_value_convertion(value):
    """
    Converts a given value to a corresponding PLC (Performance Level Category) value for the UL property 'High-Voltage Arc Tracking Rate'.

    Parameters:
    value (int): The value to be converted to a PLC value.

    Returns:
    str: The PLC value as a string.
    """

    if value > 150:
        return "plc 4"
    elif value >= 80.1:
        return "plc 3"
    elif value >= 25.5:
        return "plc 2"
    elif value >= 10.1:
        return "plc 1"
    else:
        return "plc 0"
    
def arc_value_convertion(value):
    """
    Converts a given value to a corresponding PLC (Performance Level Category) value for the UL property 'Arc Resistance'.

    Parameters:
    value (int): The value to be converted to a PLC value.

    Returns:
    str: The PLC value as a string.
    """

    if value >= 420:
        return "plc 0"
    elif value >= 360:
        return "plc 1"
    elif value >= 300:
        return "plc 2"
    elif value >= 240:
        return "plc 3"
    elif value >= 180:
        return "plc 4"
    elif value >= 120:
        return "plc 5"
    elif value >= 60:
        return "plc 6"
    else:
        return "plc 7"

def get_entities(query,ner_prompt,deployment_name):
    """
    Extracts named entities from a given query text using Azure OpenAI's chat completion API.

    This function sends a query to Azure OpenAI's model (finetuned for NER) to identify and extract named entities based on 
    a provided NER (Named Entity Recognition) prompt. It acts as a wrapper around the Azure OpenAI API call.

    Parameters:
        query (str): The text from which entities should be extracted. This is typically a 
                    preprocessed search query.
        ner_prompt (str): The system prompt that instructs the model how to perform NER extraction.
                         This defines the entities to look for and extraction rules.
        deployment_name (str): The name of the Azure OpenAI model deployment to use for inference.

    Returns:
        str: The model's response containing the extracted named entities in a structured format. The exact format depends on the how the model was trained.

    Logic:
        1. The function uses a fixed random seed (12) for reproducibility
        2. Uses a very low temperature (0.01) to make outputs more deterministic
        3. Sends the query as a chat completion request with:
           - System message containing the NER prompt
           - User message containing the query text
        4. Returns only the content of the model's response message
    """

    completion = client.chat.completions.create(
        seed=12,
        temperature = 0.01,
        model=deployment_name,
        messages=[
            {"role": "system", "content": ner_prompt}, 
            {"role": "user", "content": query},
            ],
        )

    return completion.choices[0].message.content

def update_auto_cert(cert, oem, auto_certs):
    """
    Updates the list of auto-certifications for a given OEM.

    This function ensures that the auto-certifications are correctly labeled.

    Parameters:
    cert (str): The certification to be added or updated.
    oem (str): The OEM associated with the certification.
    auto_certs (list): The list of auto-certifications to be updated.

    Returns:
    list: The updated list of auto-certifications.

    Note:
    - This function is mainly used if the model is not able to identify the auto-certifications and was misclassified as grade / competitor grade.
    """

    if {'oem': 'all', 'certs': ['all']} in auto_certs:
        auto_certs.remove({'oem': 'all', 'certs': ['all']})

    oem_found = False
    for auto_cert in auto_certs:
        if auto_cert['oem'] == oem:
            oem_found = True
            cert_found = False
            if 'all' in auto_cert['certs']:
                auto_cert['certs'].remove('all')

            if cert not in auto_cert['certs']:
                for cert_labelled in auto_cert['certs']:
                    if re.sub(r'\W+', '', cert).lower() == re.sub(r'\W+', '', cert_labelled).lower():
                        cert_found = True

                if not cert_found:
                    auto_cert['certs'].append(cert)

    if not oem_found:
        auto_certs.append({'oem': oem, 'certs': [cert]})

    return auto_certs

def validate_auto_cert(sq, labelled_certs, norm_auto_certs):
    """
    Validates the list of auto-certifications identified by the model.

    This function ensures that the auto-certifications and oems are correctly mapped and 
    adds "{'oem': 'all', 'certs': ['all']}" if auto certification is empty when "auto approval"/"auto certification" is present in the query.
    It also checks for duplicate certifications and ensures that each certification is unique.

    Parameters:
    sq (str): The search query string.
    labelled_certs (list): The list of auto-certifications to be validated.
    norm_auto_certs (list): The list of normalized auto-certifications.

    Returns:
    list: The validated list of auto-certifications.
    """

    temp = []
    temp = [x for x in labelled_certs if x not in temp]

    all_auto = {'oem': 'all', 'certs': ['all']}
    all_auto_phrases = ['auto certi', 'auto appr', 'auto spec', 'automotive appr', 'automotive cert', 'automotive spec']
    if len(labelled_certs)>1 and all_auto in labelled_certs:
        labelled_certs.remove(all_auto)
    elif labelled_certs == [all_auto]:
        return labelled_certs
    elif not labelled_certs and any(x in sq for x in all_auto_phrases):
        print('all auto cert not labelled by model. Adding it')
        return [all_auto]
    
    validated_data = {}
    for auto_cert in labelled_certs:
        if 'all' in auto_cert['certs']:
            validated_data[auto_cert['oem']] = auto_cert['certs']
            continue
        
        for cert in auto_cert['certs']:
            cert_norm = re.sub(r'\W+', '', cert).lower()
            auto_cert_match = False
            cert_match = False
            temp = []
            for norm_auto in norm_auto_certs:
                if cert_norm in norm_auto[0] and auto_cert['oem']==norm_auto[1]:
                    cert_match = False
                    auto_cert_match = True
                    if auto_cert['oem'] in validated_data:
                        validated_data[auto_cert['oem']].append(cert)
                    else:
                        validated_data[auto_cert['oem']] = [cert]

                elif cert_norm in norm_auto[0]:
                    cert_match = True
                    temp = [cert, norm_auto[1]]

            if cert_match and not auto_cert_match:
                print(f'mapping {cert} to OEM: {temp[1]}')
                if temp[1] in validated_data:
                    validated_data[temp[1]].append(temp[0])
                else:
                    validated_data[temp[1]] = [temp[0]]
            elif not cert_match and not auto_cert_match:
                if auto_cert['oem']=='all' and auto_cert['certs']!=['all']:
                    continue
                elif auto_cert['oem'] in validated_data:
                    validated_data[auto_cert['oem']].append(cert)
                else:
                    validated_data[auto_cert['oem']] = [cert]
    
    validated_certs = []
    for oem in validated_data:
        validated_certs.append({'oem': oem, 'certs': list(set(validated_data[oem]))})
    return validated_certs

def get_industry(application):
    """
    This function takes an application and returns the corresponding industry
    from a predefined list, or None if no industry is found.

    Args:
      application: A string describing the application.

    Returns:
      A string representing the industry or None if not found.

    Note:
    - This function was used in the older versions where the model was not trained to identify industry and is not used currently.
    """
    #separate logic for Electrical & Electronics
    if "electrical" in  application and "electronic" in application:
        return "Electrical & Electronics"
    
    application = re.sub(r'\be\s*&\s*e\b', 'e_and_e', application, flags=re.IGNORECASE)

    stop_words = ["an", "and", "are", "as", "at", "be", "but", "by", "for", "if", "in", "into", "is",
                    "it", "no", "not", "of", "on", "or", "such", "that", "the", "their", "then", "there",
                    "these", "they", "this", "to", "was", "will", "with"]
    app_keywords = [i for i in re.split(r'[ -/&]+', application) if i not in stop_words]

    app_keywords = ['e & e' if i == 'e_and_e' else i for i in app_keywords]
    
    industries = {
        "Medical & Pharma": ["pharma", "pharmaceutical", "biotechnology", "biomedical", "medical & pharma"],

        "Industrial": ["factory", "manufacturing","engineering"],

        "Automotive & Transportation": ["automotive", "automobility", "transportation", "transport"],

        "Consumer Goods": ["consumer", "retail"],

        "Electrical & Electronics": ["e & e", "electrical", "electronics", "e&e", "e and e", "pv"]
    }
    
    for app_keyword in app_keywords:
        matching_industries = [industry for industry, keywords in industries.items() if any(keyword in app_keyword and len(keyword)/len(app_keyword)>=0.8 for keyword in keywords)]  
        if matching_industries:
            return matching_industries[0]
    
    return None

def check_for_terms(sq, terms):
    """
    Checks if any of the specified terms are present in the given search query.

    Parameters:
    sq (str): The search query string.
    terms (list): A list of terms to check for in the search query.

    Returns:
    bool: True if any of the terms are found in the search query, False otherwise.

    Note:
    - This function is used for terms like "eco-c", "eco-r", "eco-b", "eco", "ecomid" etc.
    """

    is_match = False
    sq = sq.replace("-", " - ").replace("/", " / ")
    sq = re.sub("(\s+)", " ", sq.strip())
    is_match = any(re.compile(r'\b({0})\b'.format(term)).search(sq) for term in terms)
    return is_match


def run_ner(search_query: str, DEPENDENCIES: dict, user_type: str):
    """
    Processes a search query to identify and extract named entities that Chemille can handle.

    This function serves as the main entry point for Named Entity Recognition (NER) processing. It takes a raw
    search query, processes it through various stages of entity extraction and validation, and returns a 
    structured output containing identified entities and their classifications.

    Parameters:
    -----------
    search_query : str
        The raw search query text to be processed. This can contain material names, properties, grades,
        and other relevant information about materials.
    
    DEPENDENCIES : dict
        A dictionary containing configuration data and reference values needed for processing, including:
        - MODEL_VERSION: Version of the NER model being used
        - API_VERSION: Version of the API
        - GPT_PROMPT: Prompt template for GPT model
        - GPT_DEPLOYMENT_PROD/NPROD: GPT model deployment endpoints
        - ENVIRONMENT: Current environment (PROD/NPROD)
        - Various reference lists and mappings for validation

    Returns:
    --------
    dict
        A structured dictionary containing:
        - userInput: Original search query
        - modelOutput: 
            - entities: Identified entities categorized by type (GRADE, APPLICATION, BRAND, etc.)
            - unidentified: Parts of query that couldn't be classified
            - outOfScope: Entities that were identified but are out of scope
        - modelVersion: Version of the NER model used
        - apiVersion: Version of the API

    Logic:
    ---------------
    1. Preprocesses the search query to a clean text for NER extraction (This is handled in pre_processing.py). Along with the clean text, it also returns the normalized query for grade / competitor grade / auto certification identification.
    2. Checks and identifies if only a grade / competitor grade / auto certification is found in the query and bypasses both the NER model and post-processing validations for direct search queries. 
    3. Attempts entity extraction using primary GPT deployment and falls back to secondary deployment if primary fails. For non-prod environments, it uses only the NPROD deployment.
    4. Post-processes extracted entities through various validation steps. Mis-labelled entities (grade/competitor grade/auto certification) are corrected.
    5. Handles special cases where re-training is not required:
        - Property/UL value's unit conversion
        - Includes new business requirements which are not present in the model's training data and can be handled by rules
        - Simple fixes for existing model's issues
    6. Identifies OutOfScope entities using the OutOfScope data and pattern matching (This is handled in post_processing.py)
    7. Formats and returns the final structured output

    Note:
    - Color codes are removed from the grade if found in the grade identified.
    - "eco-c" (carbon capture) is not used in the model training and handled in post-processing.
    - During model training, "eco" synonym appeared twice and had two meanings (issue in the synonym table) "sustainable" and "ecomid". This was creating a confusion for the model. Currently, "eco" synonym is mapped to "sustainable" in post-processing.
    """

    st = time.time()
    print("user type:", user_type)

    #SAP Material ID
    search_query = search_query.strip()  # Remove leading/trailing whitespace
    if search_query.isdigit():
        # if search_query.startswith('0'):
        search_query = str(int(search_query))
        print("user search query:", search_query)
        if len(search_query) == 8 and search_query.startswith(('2', '5')):
            output_sap_material_id = {
            "userInput": {
                "searchQuery": search_query
            },
            "modelOutput": {
                "entities": {"GRADE": [],
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
                        "MATERIAL_ID": [search_query]},
                "unidentified": "",
                "outOfScope": {
                    "active": False,
                    "entities": {"GRADE": [],
                        "BRAND": [],
                        "POLYMER": [],
                        "FILLER": [],
                        "OTHERS": []}}
            },
            "modelVersion": DEPENDENCIES["MODEL_VERSION"],
            "apiVersion": DEPENDENCIES["API_VERSION"]
        }
            return output_sap_material_id #"SAP Material ID with 00000000 prefix"
    # else:
    #print("Invalid Material ID") # For debugging, can be removed later


    search_query_cleaned, query_for_grade_match = data_preprocessing(
        search_query, DEPENDENCIES["FILTERED_VALUES"], DEPENDENCIES["UNITS_LIST"], DEPENDENCIES)
    print("pre processed query : ", search_query_cleaned)
    et = time.time()
    print("dp time: ", et-st)
    if not search_query_cleaned:
        output = {
            "userInput": {
                "searchQuery": search_query
            },
            "modelOutput": {
                "entities": {"GRADE": [],
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
            "modelVersion": DEPENDENCIES["MODEL_VERSION"],
            "apiVersion": DEPENDENCIES["API_VERSION"]
        }
        return output

    NORMALIZED_UNIQUE_VALUES = DEPENDENCIES['NORMALIZED_UNIQUE_VALUES']
    ecor_pattern = r'eco\s*[\-\/\s]?\s*r$'
    ecob_pattern = r'eco\s*[\-\/\s]?\s*b$'
    ecoc_pattern = r'eco\s*[\-\/\s]?\s*c$'

    filler_abbreviations = "(cf|cd|gf|gb|gd|gx|gm|mf|md|mx|nf|af|mh|lgf|laf|lcf)"
    polymers = "(pps|pehmw|pa610|pa66|tpv|pa666|tpe|tpc|pa1010|pa6t6i|pa666t|pet|ppa|pehd|lcp|abs|pa6|pom|pa612|pa6t66|pa|tpu|peuhmw|pc|pct|pbt|pa6txt)"
    flame_values = "(5va|5vb|vo|v0|v1|v2|hb|hb40|hb75)"
    non_grade_patterns = [
        # order matters. for example: "pa66hb" is "pa66, hb" and not not equal to polymer: pa6, filler load: 6, fv: hb
        # if query is "hb11gf" # do not handle # v1810 will get formatted to "v1, 810" which is wrong as it is partial string of "kynar hsv1810"
        f"^({polymers})({flame_values})$",
        f"^({flame_values})({polymers})$",
        f"^({flame_values})({filler_abbreviations}?|{filler_abbreviations}(\d*))$",
        f"^({polymers})((\d+){filler_abbreviations}?|{filler_abbreviations}(\d*))$",
        f"^((\d+){filler_abbreviations}?|{filler_abbreviations}(\d*))({polymers})$",
        f"^((\d+){filler_abbreviations}?|{filler_abbreviations}(\d*))({flame_values})$",
        f"^({flame_values})({filler_abbreviations}?|{filler_abbreviations}(\d*))({polymers})$",
        f"^({polymers})({flame_values})({filler_abbreviations}?|{filler_abbreviations}(\d*))$",
        f"^({flame_values})({polymers})((\d+){filler_abbreviations}?|{filler_abbreviations}(\d*))$",
        f"^({polymers})((\d+){filler_abbreviations}?|{filler_abbreviations}(\d*))({flame_values})$",
        f"^((\d+){filler_abbreviations}?|{filler_abbreviations}(\d*))({flame_values})({polymers})$",
        f"^((\d+){filler_abbreviations}?|{filler_abbreviations}(\d*))({polymers})({flame_values})$",
    ]
    ignore_common_words = GRADE_OFFSET_TERMS + ["of", "for", "to", "looking", "i", "want", "show", "me", "an","a", "grades", "grade", "search", "material", "materials", "approval", "approved", "cert", "certified", "certification", "certifications", "by", 'need', 'require', 'auto', 'automotive', 'imds']

    pfas_flag, feature = False, ''

    for f in NORMALIZED_UNIQUE_VALUES['FEATURE']:
        if search_query == f[0] or search_query in f[1]:
            if f[0] == 'pfas-free':
                pfas_flag, feature = True, 'pfas-free'
            else:
                feature = f[0]

    if pfas_flag:
        output = {
                "userInput": {
                    "searchQuery": search_query
                },
                "modelOutput": {
                    "entities": {"GRADE": [],
                            "APPLICATION": [],
                            "BRAND": [],
                            "POLYMER": [],
                            "PROPERTY": [],
                            "FILLER": [],
                            "FEATURE": [feature],
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
                    "unidentified": "",
                    "outOfScope": {
                        "active": False,
                        "entities": {"GRADE": [],
                            "BRAND": [],
                            "POLYMER": [],
                            "FILLER": [],
                            "OTHERS": []}}
                },
                "modelVersion": DEPENDENCIES["MODEL_VERSION"],
                "apiVersion": DEPENDENCIES["API_VERSION"]
            }

        return output

    grade_identified = False
    competitor_grade_identified = False
    auto_cert_identified = False
    if (not any(query_for_grade_match in substring for substring in NORMALIZED_UNIQUE_VALUES['columnstoIgnore']+NORMALIZED_UNIQUE_VALUES['columnsforSubstringCheck']) or query_for_grade_match=="ultra") and\
        not re.fullmatch(r'(\d+(?:gf|mf|gb|af)|(?:gf|mf|gb|af)\d+|gf|mf|gb|af)' , query_for_grade_match) and \
        not any(re.match(p, query_for_grade_match) for p in non_grade_patterns) and \
        not bool(re.match(r'^(pbt|pet){2}$', query_for_grade_match)) and \
            len(query_for_grade_match)>2:
        
        no_offsets = False
        GRADE_OFFSET_TERMS2 = [x for x in GRADE_OFFSET_TERMS if x not in ['a', 'i']]
        search_query_normalized = re.sub(r'\W+', '', search_query_cleaned)
        #check if query matches with grades
        if query_for_grade_match in NORMALIZED_UNIQUE_VALUES['COMPETITOR_BRAND']:
            pass
        elif search_query_normalized in NORMALIZED_UNIQUE_VALUES['GRADE']:
            grade_identified = True
            no_offsets = True
        elif query_for_grade_match in NORMALIZED_UNIQUE_VALUES['GRADE']:
            grade_identified = True
        elif not any(substring == query_for_grade_match for substring in NORMALIZED_UNIQUE_VALUES['columnsforSubstringCheck']) and \
            any(query_for_grade_match in substring for substring in NORMALIZED_UNIQUE_VALUES['GRADE']):
            grade_identified=True

        grade_name_tokens = search_query_cleaned.split()
        tokens_matched = False
        grade_name_identified = ''
        if any(x in grade_name_tokens for x in ['a', 'i']):
            if 'a' in grade_name_tokens:
                positions = [i for i, v in enumerate(grade_name_tokens) if 'a' == v]  
            elif 'i' in grade_name_tokens:
                positions = [i for i, v in enumerate(grade_name_tokens) if 'i' == v] 
            else:
                positions = []

            if len(positions)==1:
                temp = [x for x in grade_name_tokens if x not in GRADE_OFFSET_TERMS2]
                temp_norm = ''.join(temp)
                temp_norm = re.sub(r'\W+', '', temp_norm)
                if temp_norm not in NORMALIZED_UNIQUE_VALUES['columnsforSubstringCheck']:
                    for nuv_grade in NORMALIZED_UNIQUE_VALUES['GRADE']:
                        if temp_norm in nuv_grade:
                            grade_name_identified = ' '.join(temp)
                            tokens_matched = True
                            grade_identified = True
                            break

            if positions and not tokens_matched:
                for idx in positions:
                    positions2 = [x for x in positions if x!=idx]
                    temp = [v for i, v in enumerate(grade_name_tokens) if i not in positions2]
                    temp = [x for x in temp if x not in GRADE_OFFSET_TERMS2]
                    temp_norm = ''.join(temp)
                    temp_norm = re.sub(r'\W+', '', temp_norm)
                    if temp_norm not in NORMALIZED_UNIQUE_VALUES['columnsforSubstringCheck']:
                        for nuv_grade in NORMALIZED_UNIQUE_VALUES['GRADE']:
                            if temp_norm in nuv_grade:
                                grade_name_identified = ' '.join(temp)
                                tokens_matched = True
                                grade_identified = True
                                break

                    if tokens_matched:
                        break
            else:
                temp_norm = ''.join(grade_name_tokens)
                temp_norm = re.sub(r'\W+', '', temp_norm)
                if temp_norm not in NORMALIZED_UNIQUE_VALUES['columnsforSubstringCheck']:
                    for nuv_grade in NORMALIZED_UNIQUE_VALUES['GRADE']:
                        if temp_norm in nuv_grade:
                            grade_name_identified = ' '.join(grade_name_tokens)
                            tokens_matched = True
                            grade_identified = True
                            break

        if grade_identified:
            print("grade identified, bypassing NER model and post-processing")
            if no_offsets:
                grade_name_identified = search_query_cleaned                
            elif not tokens_matched:
                grade_name_identified = search_query_cleaned.split()
                grade_name_identified = " ".join([substring for substring in grade_name_identified if substring not in GRADE_OFFSET_TERMS])
            elif not grade_name_identified:
                print('grade_name_identified is empty, handle this')
                grade_name_identified = search_query_cleaned.split()
                grade_name_identified = " ".join([substring for substring in grade_name_identified if substring not in GRADE_OFFSET_TERMS])

            grade_name_identified = grade_name_identified.replace(" - ","-").replace(". ",".")
            
            if search_query.lower() != search_query_cleaned:
                grade_name_identified = search_query.lower()

            result = {
                        "GRADE": [grade_name_identified],
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
                        "MATERIAL_ID":[],
                        "MEDICAL_CERT": [],
                        "CHEMICAL_RESISTANCE": []
                        }
            print("Grade identified", result)
            outOfScope = identify_out_of_scope_items(DEPENDENCIES, search_query_cleaned, result, user_type)
            
            output = {
                "userInput": {
                    "searchQuery": search_query
                },
                "modelOutput": {
                    "entities": result,
                    "unidentified": "",
                    "outOfScope": outOfScope
                },
                "modelVersion": DEPENDENCIES["MODEL_VERSION"],
                "apiVersion": DEPENDENCIES["API_VERSION"]
            }

            if not outOfScope["active"] and 'eco-r' in grade_name_identified:
                output["modelOutput"]["entities"]["FEATURE"].append("recycled content")
                output["modelOutput"]["entities"]["GRADE"].remove(grade_name_identified)

                if re.sub(ecor_pattern, '', grade_name_identified).strip():
                    print('removing eco-r in pre-processing')
                    output["modelOutput"]["entities"]["GRADE"].append(re.sub(ecor_pattern, '', grade_name_identified).strip())
            elif not outOfScope["active"] and 'eco-b' in grade_name_identified:
                output["modelOutput"]["entities"]["FEATURE"].append("bio-content")
                output["modelOutput"]["entities"]["GRADE"].remove(grade_name_identified)

                if re.sub(ecob_pattern, '', grade_name_identified).strip():
                    print('removing eco-b in pre-processing')
                    output["modelOutput"]["entities"]["GRADE"].append(re.sub(ecob_pattern, '', grade_name_identified).strip())
            elif not outOfScope["active"] and 'eco-c' in grade_name_identified:
                output["modelOutput"]["entities"]["FEATURE"].append("carbon capture")
                output["modelOutput"]["entities"]["GRADE"].remove(grade_name_identified)

                if re.sub(ecoc_pattern, '', grade_name_identified).strip():
                    print('removing eco-c in pre-processing')
                    output["modelOutput"]["entities"]["GRADE"].append(re.sub(ecoc_pattern, '', grade_name_identified).strip())

            return output
        
        #check if query matches with competitor grades
        if query_for_grade_match in NORMALIZED_UNIQUE_VALUES['COMPETITOR_GRADE']:
            competitor_grade_identified = True
        elif query_for_grade_match in NORMALIZED_UNIQUE_VALUES['COMPETITOR_BRAND']:
            competitor_grade_identified = True
        elif not any(substring == query_for_grade_match for substring in NORMALIZED_UNIQUE_VALUES['columnsforSubstringCheck']) and \
            any(query_for_grade_match in substring for substring in NORMALIZED_UNIQUE_VALUES['COMPETITOR_GRADE']) and\
                query_for_grade_match not in ["nsf"]:
            competitor_grade_identified=True
        if competitor_grade_identified:
            comp_grade_name_identified = search_query_cleaned.split()
            comp_grade_name_identified = " ".join([substring for substring in comp_grade_name_identified if substring not in GRADE_OFFSET_TERMS]).replace(" - ","-").replace(" + ","+").replace(". ",".")
            if any(p in comp_grade_name_identified for p in ["(", ")"]):
                comp_grade_name_identified = search_query.lower()

            result = {
                        "GRADE": [],
                        "APPLICATION": [],
                        "BRAND": [],
                        "POLYMER": [],
                        "PROPERTY": [],
                        "FILLER": [],
                        "FEATURE": [],
                        "PROCESSING": [],
                        "DELIVERY_FORM": [],
                        "COMPETITOR_GRADE": [comp_grade_name_identified],
                        "AUTO_CERT": [],
                        "RAILWAY_CERT": [],
                        "WATER_CERT": [],
                        "NSF_CERT": [],
                        "INDUSTRY": [],
                        "REGION": [],
                        "MATERIAL_ID":[],
                        "MEDICAL_CERT": [],
                        "CHEMICAL_RESISTANCE": []}
            
            outOfScope = identify_out_of_scope_items(DEPENDENCIES, search_query_cleaned, result, user_type)
            
            output = {
                "userInput": {
                    "searchQuery": search_query
                },
                "modelOutput": {
                    "entities": result,
                    "unidentified": "",
                    "outOfScope": outOfScope
                },
                "modelVersion": DEPENDENCIES["MODEL_VERSION"],
                "apiVersion": DEPENDENCIES["API_VERSION"]
            }
            
            return output

        # check if query matches with auto certification
        if not any(re.compile(r'\b({0})\b'.format(item), flags=re.IGNORECASE).search(search_query_cleaned) for item in ["tds", "sds"]) and \
            not any(item in search_query_cleaned for item in  ["alternatives", "alternative", "alternate", "similar", "offset", "replacement", "replace", "replacing", "in place", "inplace", "instead", "competitor", "competitors"]):
            
            query_cert =  ' '.join([x for x in search_query_cleaned.split() if x not in ignore_common_words]).replace(" - ","-").replace(" + ","+").replace(". ",".")
            query_cert_norm = re.sub(r'\W+', '', query_cert)
            if not any(query_cert_norm in substring for substring in NORMALIZED_UNIQUE_VALUES['columnstoIgnore']+NORMALIZED_UNIQUE_VALUES['columnsforSubstringCheck']) and\
                not re.fullmatch(r'(\d+gf|gf\d+|\d+mf|mf\d+|gf|mf)', query_cert_norm) and \
                not any(re.match(p, query_cert_norm) for p in non_grade_patterns) and \
                    len(query_cert_norm)>3:
            
                for auto_cert in NORMALIZED_UNIQUE_VALUES['AUTO_CERT']:
                    if query_cert_norm in auto_cert[0]:
                        auto_cert_data = {'oem': auto_cert[1], 'certs': [query_cert]}
                        auto_cert_identified = True
                        break

            if auto_cert_identified:
                print("auto_cert added using pre-processing")
                output = {
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
                            "AUTO_CERT": [auto_cert_data],
                            "RAILWAY_CERT": [],
                            "WATER_CERT": [],
                            "NSF_CERT": [],
                            "INDUSTRY": [],
                            "REGION": [],
                            "MATERIAL_ID":[]},
                        "unidentified": "",
                        "outOfScope": {
                            "active": False,
                            "entities": {"GRADE": [],
                                "BRAND": [],
                                "POLYMER": [],
                                "FILLER": [],
                                "OTHERS": []}}
                    },
                    "modelVersion": DEPENDENCIES["MODEL_VERSION"],
                    "apiVersion": DEPENDENCIES["API_VERSION"]
                }
                return output


    # elif any(re.match(p, query_for_grade_match) for p in non_grade_patterns):
    #     # polymer and filler load e.g. "pom 15%"
    #     # Do not process it to "pom, 15%" as the model may / may not identify the filler load
    #     poly_tl_patterns = [
    #         f"^({polymers}) (\d+)$",
    #         f"^({polymers})(\d+)$",
    #         f"^({polymers}) (\d+)%$",
    #         f"^({polymers})(\d+)%$",
    #         f"^(\d+)% ({polymers})$",
    #         f"^(\d+)%({polymers})$",
    #         f"^(\d+) ({polymers})$",
    #         f"^(\d+)({polymers})$",
    #     ]
        
    #     sq_filtered = re.sub(r'[^a-zA-Z0-9 %]', ' ', search_query_cleaned)
    #     sq_filtered =  ' '.join([x for x in sq_filtered.split() if x not in ignore_common_words])
    #     if any(re.match(p, sq_filtered) for p in poly_tl_patterns):
    #        print("Skipping polymer_filler_fv formatting as it can be a polymer filler load pattern: ", search_query_cleaned)
    #     else:
    #         for non_grade_pattern in non_grade_patterns:
    #             # print(non_grade_pattern)
    #             # Match and format  
    #             match = re.match(non_grade_pattern, query_for_grade_match)  
    #             if match:  
    #                 break

    #         fv_sorted = sorted(flame_values.strip('()').split('|'), key=len, reverse=True)
    #         polymers_sorted = sorted(polymers.strip('()').split('|'), key=len, reverse=True)

    #         search_query_formatted = query_for_grade_match
    #         # print(search_query_formatted)
    #         if match and search_query_formatted not in polymers_sorted:
    #             for i in fv_sorted:
    #                 if i in set(list(match.groups())):
    #                     if search_query_formatted.startswith(i):
    #                         search_query_formatted = i + ", " + "".join(search_query_formatted.split(i))
    #                     elif len(search_query_formatted.split(i))==2:
    #                         search_query_formatted = search_query_formatted.split(i)[0] + ", " + i + ", " + search_query_formatted.split(i)[1]
    #                     else:
    #                         search_query_formatted = "".join(search_query_formatted.split(i)) + ", " + i
                
    #                     break
                            
    #             # print(search_query_formatted)
    #             for i in polymers_sorted:
    #                 if i in set(list(match.groups())):
    #                     if search_query_formatted.startswith(i):
    #                         search_query_formatted = i + ", " + "".join(search_query_formatted.split(i))
    #                     elif len(search_query_formatted.split(i))==2:
    #                         search_query_formatted = search_query_formatted.split(i)[0] + ", " + i + ", " + search_query_formatted.split(i)[1]
    #                     else:
    #                         search_query_formatted = "".join(search_query_formatted.split(i)) + ", " + i
                            
    #                     search_query_formatted =  search_query_formatted.replace(", ,", ",").strip(", ")  # for fv and polymer      
                        
    #                     break
                    
    #         search_query_cleaned = search_query_formatted
    #         print("polymer_filler_fv formatted:", search_query_cleaned)

    if DEPENDENCIES["ENVIRONMENT"]=="NPROD":
        GPT_DEPLOYMENT_MAIN=DEPENDENCIES['GPT_DEPLOYMENT_NPROD']
        GPT_DEPLOYMENT_SECONDARY=DEPENDENCIES['GPT_DEPLOYMENT_PROD']
    else:
        GPT_DEPLOYMENT_MAIN=DEPENDENCIES['GPT_DEPLOYMENT_PROD']
        GPT_DEPLOYMENT_SECONDARY=DEPENDENCIES['GPT_DEPLOYMENT_NPROD']
    try:
        result = get_entities(search_query_cleaned, DEPENDENCIES["GPT_PROMPT"], GPT_DEPLOYMENT_MAIN)
    except:
        print("Primary GPT Deployment invoke failed")
        if DEPENDENCIES["ENVIRONMENT"]=="PROD":
            result = get_entities(search_query_cleaned, DEPENDENCIES["GPT_PROMPT"], GPT_DEPLOYMENT_SECONDARY)

    try:
        result = eval(result)
    except:
        print("Output structure is invalid: ", result)
        result = {
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
                        "MATERIAL_ID": [],
                        "MEDICAL_CERT": [],
                        "CHEMICAL_RESISTANCE": []}
    
    print("Model Output: ", result)
    _ = validate_result_dict(result)

    if result['CHEMICAL_RESISTANCE']:
        if "diesel fuel" in search_query or search_query.lower() == "diesel fuel":
            result['CHEMICAL_RESISTANCE'] = [{'chemical_category': 'fuels', 'chemical_sub_category': 'diesel fuel', 'temperature': '23', 'resistance_level': 'resistant, long-term exposure'}]
        else:
            chemical_resistance_validated = validate_chemical_resistance_values(result)
            result['CHEMICAL_RESISTANCE'] = chemical_resistance_validated['CHEMICAL_RESISTANCE']

    if 'chemical resistant' in result['FEATURE']:
        print("chemical resistant feature found, adding chemical resistance entity")
        feature_remapped = reclassify_feature_to_chem_res(result, search_query_cleaned)
        result['CHEMICAL_RESISTANCE'] = feature_remapped['CHEMICAL_RESISTANCE']
        result['FEATURE'].remove('chemical resistant')

    if result['MEDICAL_CERT']:
        medical_cert_validated = validate_medical_cert_values(result)
        result['MEDICAL_CERT'] = medical_cert_validated['MEDICAL_CERT']
        
    if result['FEATURE']:
        feature_validated = validate_feature_for_med_cert(result)
        result['FEATURE'] = feature_validated['FEATURE']
        result['MEDICAL_CERT'] = feature_validated['MEDICAL_CERT']

    if result['FILLER']:
        for filler in result['FILLER']: #iterating over list of FILLER values
            if isinstance(filler, dict) and 'total_load' in filler:
                min_val = filler['total_load']['min']
                max_val =  filler['total_load']['max']
                val = filler['total_load']['value']
                
                if val in (min_val, max_val):
                    filler['total_load']['value'] = None
        
        if any('celstran' in brand.lower() for brand in result['BRAND']):
            celstran_fillers = {'aramid fiber': 'long aramid fiber', 'carbon fiber': 'long carbon fiber', 'glass fiber': 'long glass fiber'}

            for filler in result['FILLER']: 
                if 'filler_name' in filler and isinstance(filler['filler_name'], list):
                    filler_names = filler['filler_name']
                    print('Filler names:', filler_names, '\n')

            final_filler = []

            for f in filler_names:
                if f.lower() in celstran_fillers.values():
                    final_filler.append(f)
                elif f.lower() in search_query.lower():
                    final_filler.append(celstran_fillers.get(f.lower(), f))
                else:
                    result['FILLER'][0]['filler_name'].remove(f)
                    
            result['FILLER'][0]['filler_name'] = final_filler

    if result['PROPERTY']:
        for property in result['PROPERTY']: #iterating over list of PROPERTY values
            if isinstance(property, dict) and 'modifier' in property: #checks for the 'modifier' key
                min_val = property['modifier']['min']
                max_val =  property['modifier']['max']
                val = property['modifier']['value']
                
                if val in (min_val, max_val):
                    property['modifier']['value'] = None
    if result['BRAND']:
        for brand in result['BRAND']:
            if brand.lower() in NORMALIZED_UNIQUE_VALUES['BRAND']:
                pass
            elif result["BRAND"] == ['bexloy']:
                result["BRAND"] = ['hytrel']
            elif 'selar' in result['BRAND']:
                result['GRADE'].append('selar')
                result['BRAND'].remove('selar')
            else:
                result['BRAND'].remove(brand)

    if search_query_cleaned in ['electrical sustainable', 'sustainable electrical']:
        result['APPLICATION'] = ['electrical']
        result['FEATURE'] = ['sustainable']

    def check_if_uv_in_grade(grade_name):
        """
        Checks if UV is present in the grade name and removes it if present.
        It also formats the grade name.

        Returns:
            tuple:
            - A boolean value "uv_status" which is used to add UV to the feature list
            - The grade name with UV removed
        """

        uv_pattern = r'(?:(?<=\W)|(?<=^)|(?<=\d))(uv)(?=\W|$|\d)' 
        uv_status = bool(re.search(uv_pattern, grade_name))
        if uv_status:
            grade_name = re.sub(r'(?<![a-zA-Z])\W*uv$' , '', grade_name).strip().replace(" - ","-").replace(". ",".").replace("eco r","eco-r").replace("eco b","eco-b").replace("eco c","eco-c")
        else:
            grade_name = grade_name.replace(" - ","-").replace(". ",".").replace("eco r","eco-r").replace("eco b","eco-b").replace("eco c","eco-c")
        return uv_status, grade_name
    
    #check if predicted competitor are from grades
    if not grade_identified and not competitor_grade_identified:
        for competitor_grade in result["COMPETITOR_GRADE"]:
            competitor_grade_normalized = re.sub(r'\W+', '', competitor_grade).lower()
            if competitor_grade in NORMALIZED_UNIQUE_VALUES['COMPETITOR_BRAND']:
                pass
            elif any(competitor_grade_normalized in substring for substring in NORMALIZED_UNIQUE_VALUES['GRADE']):
                result["COMPETITOR_GRADE"].remove(competitor_grade)
                result["GRADE"].append(competitor_grade)
            elif any(re.compile(r'\b({0})\b'.format(item), flags=re.IGNORECASE).search(search_query_cleaned) for item in ["tds", "sds"]) or \
                any(item in search_query_cleaned for item in  ["alternatives", "alternative", "alternate", "similar", "offset", "replacement", "replace", "replacing", "in place", "inplace", "instead", "competitor"]):
                pass
            elif any(competitor_grade_normalized in auto_cert[0] for auto_cert in NORMALIZED_UNIQUE_VALUES['AUTO_CERT']) \
                and not any(competitor_grade_normalized in cg for cg in NORMALIZED_UNIQUE_VALUES['COMPETITOR_GRADE']):
                for auto_cert in NORMALIZED_UNIQUE_VALUES['AUTO_CERT']:
                    if competitor_grade_normalized in auto_cert[0]:
                        print("found auto_cert in comp_grade but in an comp_grade list")
                        result["COMPETITOR_GRADE"].remove(competitor_grade)
                        result['AUTO_CERT'] = update_auto_cert(competitor_grade, auto_cert[1], copy.deepcopy(result['AUTO_CERT']))
                        break
            elif process.extract(competitor_grade, DEPENDENCIES["GRADE_NAMES"], scorer=fuzz.token_sort_ratio, limit=1)[0][1] > 80:
                result["COMPETITOR_GRADE"].remove(competitor_grade)
                result["GRADE"].append(competitor_grade)
            else:
                pass
          
        for grade in result["GRADE"]:
            grade_normalized = re.sub(r'\W+', '', grade).lower()
            if any(grade_normalized in substring for substring in NORMALIZED_UNIQUE_VALUES['GRADE']):
                pass
            elif any(grade_normalized in substring for substring in NORMALIZED_UNIQUE_VALUES['COMPETITOR_GRADE']):
                result["GRADE"].remove(grade)
                result["COMPETITOR_GRADE"].append(grade)
            elif any(grade_normalized in auto_cert[0] for auto_cert in NORMALIZED_UNIQUE_VALUES['AUTO_CERT']):
                for auto_cert in NORMALIZED_UNIQUE_VALUES['AUTO_CERT']:
                    if grade_normalized in auto_cert[0]:
                        print("found auto_cert in grade")
                        result["GRADE"].remove(grade)
                        result['AUTO_CERT'] = update_auto_cert(grade, auto_cert[1], copy.deepcopy(result['AUTO_CERT']))
                        break
            # elif rprocess.extractOne(grade, DEPENDENCIES["GRADE_NAMES"], scorer=rfuzz.token_sort_ratio)[1] > 85 \
            #     and not any(x in grade for x in DEPENDENCIES['OUT_OF_SCOPE_DATA']['brands']): #scorer=fuzz.token_sort_ratio, limit=1)[0][1] <= 50
            #     result["GRADE"].remove(grade)
            #     result["COMPETITOR_GRADE"].append(grade)
            
            elif any(
                grade_normalized.startswith(re.sub(r'\W+', '', brand).lower())
                for brand in NORMALIZED_UNIQUE_VALUES['BRAND']
            ):
                # Grade starts with a known brand → keep it as GRADE
                pass

            elif process.extract(grade, DEPENDENCIES["GRADE_NAMES"], scorer=fuzz.token_sort_ratio, limit=1)[0][1] > 80 \
                and not any(x in grade for x in DEPENDENCIES['OUT_OF_SCOPE_DATA']['brands']): #scorer=fuzz.token_sort_ratio, limit=1)[0][1] <= 50
                result["GRADE"].remove(grade)
                result["COMPETITOR_GRADE"].append(grade)
            else:
                pass
    
        if not auto_cert_identified:
            for cert_detials in result['AUTO_CERT']:
                if 'certs' in cert_detials and 'all' not in cert_detials['certs'] and cert_detials['oem'] != 'all':
                    for cert in cert_detials['certs']:
                        cert_normalized = re.sub(r'\W+', '', cert).lower()
                        if any(cert_normalized in auto_cert[0] for auto_cert in NORMALIZED_UNIQUE_VALUES['AUTO_CERT']):
                            pass
                        elif cert_normalized in NORMALIZED_UNIQUE_VALUES['GRADE'] \
                            and cert_detials['oem'] not in search_query_cleaned:
                            cert_detials['certs'].remove(cert)
                            result["GRADE"].append(cert)
                        elif cert_normalized in NORMALIZED_UNIQUE_VALUES['COMPETITOR_GRADE'] \
                            and cert_detials['oem'] not in search_query_cleaned:
                            cert_detials['certs'].remove(cert)
                            result["COMPETITOR_GRADE"].append(cert)
                        
                    if not cert_detials['certs']:
                        # result['AUTO_CERT'].remove(cert_detials)
                        cert_detials['certs'].append('all')

    if "blueridge" in result["GRADE"]:
        result["GRADE"].remove("blueridge")
        result["BRAND"].append("blueridge")
    if "litepol" in result["GRADE"]:
        result["GRADE"].remove("litepol")
        result["BRAND"].append("litepol")
    if "hostaform" in result["BRAND"] and "hostaform" not in search_query_cleaned and "at" in search_query_cleaned:
        result["BRAND"].remove("hostaform")
    if "africa middle east" in result["REGION"]:
        result["REGION"].remove("africa middle east")
        result["REGION"].append("europe middle east africa")
    #Remove competitor name from competitor grade names
    if result["COMPETITOR_GRADE"]:
        for competitor_grade in result["COMPETITOR_GRADE"]: 
            competitor_grade_words = competitor_grade.split()
            # Remove words from the start 
            while competitor_grade_words and competitor_grade_words[0].lower() in DEPENDENCIES['NORMALIZED_COMPETITOR_NAMES']:  
                competitor_grade_words.pop(0)

            # Remove words from the end  
            while competitor_grade_words and competitor_grade_words[-1].lower() in DEPENDENCIES['NORMALIZED_COMPETITOR_NAMES']:  
                competitor_grade_words.pop() 

            competitor_grade_modified = ' '.join(competitor_grade_words).strip().replace(" - ","-").replace(" + ","+").replace(". ",".")
            result["COMPETITOR_GRADE"].remove(competitor_grade)
            if competitor_grade_modified!="":
                result["COMPETITOR_GRADE"].append(competitor_grade_modified)
    #Add uv resitance in feature if uv present in grade name
    if result["GRADE"]:
        all_brands =  list(set(DEPENDENCIES['OUT_OF_SCOPE_DATA']['brands'] + NORMALIZED_UNIQUE_VALUES['BRAND']))
        for grade in result["GRADE"]: 
            uv_status, revised_grade_name = check_if_uv_in_grade(grade)
            result["GRADE"].remove(grade)
            result["GRADE"].append(revised_grade_name)
            if uv_status:
                result["FEATURE"] = list(set(result["FEATURE"]+["u.v. stabilized or stable to weather"]))

            if 'eco-r' in revised_grade_name:
                result["FEATURE"].append("recycled content")
                result["GRADE"].remove(revised_grade_name)

                if re.sub(ecor_pattern, '', revised_grade_name).strip():
                    print('removing eco-r in post-processing')
                    revised_grade_name = re.sub(ecor_pattern, '', revised_grade_name).strip()
                    result["GRADE"].append(revised_grade_name)

            elif 'eco-b' in revised_grade_name:
                result["FEATURE"].append("bio-content")
                result["GRADE"].remove(revised_grade_name)

                if re.sub(ecob_pattern, '', revised_grade_name).strip():
                    print('removing eco- in post-processing')
                    revised_grade_name = re.sub(ecob_pattern, '', revised_grade_name).strip()
                    result["GRADE"].append(revised_grade_name)

            elif 'eco-c' in revised_grade_name:
                result["FEATURE"].append("carbon capture")
                result["GRADE"].remove(revised_grade_name)

                if re.sub(ecoc_pattern, '', revised_grade_name).strip():
                    print('removing eco- in post-processing')
                    revised_grade_name = re.sub(ecoc_pattern, '', revised_grade_name).strip()
                    result["GRADE"].append(revised_grade_name)

            if revised_grade_name in all_brands:
                result["BRAND"].append(revised_grade_name)
                result["GRADE"].remove(revised_grade_name)
    
    if result["POLYMER"]:
        if "pbt" in result["POLYMER"] and "polyester" in search_query_cleaned and "pbt" not in search_query_cleaned:
            result["POLYMER"].remove("pbt")
            result["POLYMER"].append("polyester")

    if result["AUTO_CERT"] or any(x in search_query_cleaned for x in ['auto certi', 'auto appr']):
        result["AUTO_CERT"] = validate_auto_cert(search_query_cleaned, result["AUTO_CERT"], NORMALIZED_UNIQUE_VALUES['AUTO_CERT'])

    if result["RAILWAY_CERT"]:
        result["RAILWAY_CERT"][0]["hazard_level"] = list(set([re.sub(r'\W+','', s).lower() for s in result["RAILWAY_CERT"][0]["hazard_level"]]))
        result["RAILWAY_CERT"][0]["req_set"] = list(set([re.sub(r'\W+','', s).lower() for s in result["RAILWAY_CERT"][0]["req_set"]]))

    if result["PROCESSING"]:
        if 'fibre spinning / gel extrusion' in result["PROCESSING"]:
            result["PROCESSING"].remove("fibre spinning / gel extrusion")
            result["PROCESSING"].append("fiber spinning / gel spinning")

    if 'moulding' in search_query_cleaned and not any("molding" in i for i in result["PROCESSING"]) or (re.search(r'\bmolding\b.*\bgrade\b|\bgrade\b.*\bmolding\b', search_query_cleaned) and not any("molding grade" in i for i in result["PROCESSING"])):
        result["PROCESSING"].append("molding")


    if len(result["FEATURE"])>0:
        if "heat stabilized" in result["FEATURE"]:
            result["FEATURE"].remove("heat stabilized")
            result["FEATURE"].append("heat stabilized or stable to heat")
        if "impact modified" in result["FEATURE"]:
            result["FEATURE"].remove("impact modified")
            result["FEATURE"].append("high impact or impact modified")
        if "bio-based" in result["FEATURE"]:
            result["FEATURE"].remove("bio-based")
            result["FEATURE"].append("bio-content")
        if "contains recycle" in result["FEATURE"]:
            result["FEATURE"].remove("contains recycle")
            result["FEATURE"].append("recycled content")

        result["FEATURE"] = [x for x in result["FEATURE"] if not 'auto' in x]
    
    carbon_strings = ['carbon footprint', 'iso 14067', 'iso14067', 'carbon capture and utilization', 'ccu', 'carbon capture']
    if any(re.search(r'\b' + re.escape(substring) + r'\b', search_query_cleaned) for substring in carbon_strings):
        result["FEATURE"].append("carbon capture")
        result["FEATURE"] = list(set(result["FEATURE"]))
    
    def plural_to_singular(word):  
        """
        Converts plural to singular. 
        Used for Application field.

        Note:
        - Was used in older versions of the model. Currently, it is not used.
        """

        # Common rules for converting plural to singular  
        if word.endswith('ies'):  
            return word[:-3] + 'y'  
        elif word.endswith('es'):  
            return word[:-2]  
        elif word.endswith('s') and not word.endswith('ss'):  
            return word[:-1]  
        else:  
            return word

    def remove_specific_words_from_application(text, words_set): 
        """
        Removes specific words from the beginning and end of an application text string.

        This function cleans application text by removing specified words from both the start and end
        of the text. It is primarily used to standardize application descriptions by removing common
        generic terms that don't add specific meaning.

        Parameters:
        -----------
        text : str
            The application text string to be cleaned
        words_set : set
            A set of words to be removed from the start and end of the text

        Returns:
        --------
        str
            The cleaned text with specified words removed from start and end

        Logic:
        ------
        1. Splits the text into individual words
        2. Removes common articles ('a', 'an', 'the', 'in') and the word 'possibly'
        3. Iteratively removes words from the start of the text if they match words in words_set
        4. Iteratively removes words from the end of the text if they match words in words_set
        5. Additionally removes 'for' and 'with' from start and end
        6. Joins remaining words back into a string

        Example:
        --------
        >> remove_specific_words_from_application("dishwasher parts", {"part","parts","material","materials"})
        "dishwasher"
        """

        # Split the text into words  
        text_words = text.split()
        text_words = [x for x in text_words if x not in ['possibly','a', 'an', 'the', 'in']]
        # text_words = [plural_to_singular(word) for word in text.split()] 
        
        # Remove words from the start  
        while text_words and text_words[0].lower() in words_set:  
            text_words.pop(0)  
        
        # Remove words from the end  
        while text_words and text_words[-1].lower() in words_set:  
            text_words.pop()  

        while text_words and text_words[0].lower() in ['for','with']:  
            text_words.pop(0) 
        while text_words and text_words[-1].lower() == ['for','with']:  
            text_words.pop()  

        # Join the remaining words back into a string  
        cleaned_text = ' '.join(text_words).strip()
        
        return cleaned_text

    if len(result["APPLICATION"])>0:
        if "medical" in result["APPLICATION"]:
            matching_medical_applications = [item for item in result["APPLICATION"] if 'medical' in item]
            for matched_med_app in matching_medical_applications:
                result["APPLICATION"].remove(matched_med_app)
                result["FEATURE"].append('medical/healthcare')

        # old issue: li auto is not being identified as auto certification
        if "li auto" in result["APPLICATION"]:
            result["APPLICATION"].remove("li auto")
            result["AUTO_CERT"].append({'oem': 'li auto', 'certs': ['all']})
        
        words_to_remove = {"part","parts","material","materials"}
        result["APPLICATION"] = [remove_specific_words_from_application(item, words_to_remove) for item in result["APPLICATION"] if item!="material handling"]
    
    ##########################
    # Electrical & Electronics
    ##########################
    ee_match = False
    ee_pattern = r'\b(electrical)s?\s*(and|\/|\-|or)\s*(electronic)s?\b' 
    if re.search(ee_pattern, search_query_cleaned):
        ee_match = re.search(ee_pattern, search_query_cleaned)
        ee_term = ee_match.group(0)

    ee_pattern = r'\b(electronic)s?\s*(and|\/|\-|or)\s*(electrical)s?\b'
    if not ee_match and re.search(ee_pattern, search_query_cleaned):
        ee_match = re.search(ee_pattern, search_query_cleaned)
        ee_term = ee_match.group(0)

    if not ee_match and re.compile(r'\b({0})\b'.format("e & e")).search(search_query_cleaned):
        ee_match = True
        ee_term = "e & e"

    if not ee_match and re.compile(r'\b({0})\b'.format("e and e")).search(search_query_cleaned):
        ee_match = True
        ee_term = "e and e"

    if not ee_match and re.compile(r'\b({0})\b'.format("electrical")).search(search_query_cleaned):
        ee_match = True
        ee_term = "electrical"

    if not ee_match and re.compile(r'\b({0})\b'.format("electronics")).search(search_query_cleaned):
        ee_match = True
        ee_term = "electronics"
    
    if ee_match:  
        add_ee_app = False
        for app in result["APPLICATION"]:
            if ee_term not in app:
                add_ee_app = True
                break
        
        #if add_ee_app or not result["APPLICATION"]:    
        #    result["APPLICATION"].append(ee_term)
            
        if not "electrical & electronics" in result["INDUSTRY"]:
            result["INDUSTRY"].append("electrical & electronics")

    #identify industry synonyms
    industry = get_industry(search_query_cleaned)
    industries = ["Medical & Pharma", "Industrial", "Automotive & Transportation", "Consumer Goods", "Electrical & Electronics"]
    exception_list_features = [["bio-content"], ["medical/healthcare"], ["electrical"]]
    exception_list_applications = [["pharma"], ["pharmaceutical"], ["medical & pharma"], ["manufacturing"], ["automotive"], ["automobility"], ["transportation"], ["transport"], ["e&e"], ["biotechnology"], ["engineering"], ["electronics"], ["factory"], ["automotive & transportation"], ["consumer"], ["consumer goods"], ["electrical and electronics"], ["electrical & electronics"], ["e & e"]]
    exception_list_ee_applications = ["pv", "hv", "tb", "sim", "lv", "vcm", "rf", "hsd", "ic", "ff", "ac", "wtb", "ff ccm"]

    if industry in industries:
        if result["INDUSTRY"] != " ":
            result["INDUSTRY"].append(industry)
            if result["FEATURE"] in exception_list_features:
                result["FEATURE"] = ""
            if result["APPLICATION"] in exception_list_applications:
                result["APPLICATION"] = ""
            if result["APPLICATION"] == ["retail"]:
                result["APPLICATION"] = ""
                result["INDUSTRY"].pop(0)
            if result["PROCESSING"] == ["manufacturing"]:
                result["PROCESSING"] = ""

    if search_query_cleaned in exception_list_ee_applications:
        result["APPLICATION"] = [''.join(search_query)]
        if result.get("INDUSTRY"):
            result["INDUSTRY"].pop(0)# == " " 
        if result.get("GRADE"):
            result["GRADE"].pop(0)
        if result.get("FEATURE"):
            result["FEATURE"].pop(0)
        if result.get("COMPETITOR GRADE"):
            result["COMPETITOR GRADE"].pop(0)

    ######################
    # eco terms validation
    ######################

    is_ecoc = check_for_terms(search_query_cleaned, ['ecoc', 'eco c', 'eco - c', 'eco / c'])
    is_ecob = check_for_terms(search_query_cleaned, ['ecob', 'eco b', 'eco - b', 'eco / b'])
    is_ecor = check_for_terms(search_query_cleaned, ['ecor', 'eco r', 'eco - r', 'eco / r'])
    is_ecomid = check_for_terms(search_query_cleaned, ['ecomid', 'eco mid', 'eco-mid'])

    if is_ecoc and 'carbon capture' not in result['FEATURE']:
        result['FEATURE'].append('carbon capture')

        remove_ecoc_prop = None
        if result["PROPERTY"]:
            for pd in result["PROPERTY"]:
                if pd['property_name']=='carbon capture':
                    remove_ecoc_prop = pd
                    break
        if remove_ecoc_prop:
            print("Removing carbon capture (eco-c) from property")
            result["PROPERTY"].remove(remove_ecoc_prop)

    if is_ecob and "bio-content" not in result['FEATURE']:
        result["FEATURE"].append("bio-content")

    if is_ecor and "recycled content" not in result['FEATURE']:
        result["FEATURE"].append("recycled content")

    if not is_ecomid and "ecomid" in result['BRAND']:
        if any([is_ecoc, is_ecob, is_ecor]):
            result["BRAND"].remove("ecomid") 
        elif check_for_terms(search_query_cleaned, ['eco']):
            result["BRAND"].remove("ecomid")
            result["FEATURE"].append("sustainable")


    def ul_property_value_conversion(property_modifier,conversion_function):
        """
        Converts the value of a Property/UL to a new value (category) based on a conversion function.
        It also sets the 'min' and 'max' values to None.

        Parameters:
        -----------
        property_modifier : dict
            A dictionary containing the property modifier information
        conversion_function : function
            A function that takes a value and returns a new value
        """

        try:
            if isinstance(property_modifier["modifier"]["value"], (int, float)):
                property_modifier["modifier"]["value"] = conversion_function(property_modifier["modifier"]["value"])
                property_modifier["modifier"]['min'] = property_modifier["modifier"]['max'] = None
            else:
                property_modifier["modifier"]["value"] = conversion_function(eval(property_modifier["modifier"]["value"]))
                property_modifier["modifier"]['min'] = property_modifier["modifier"]['max'] = None
        except: 
            # rules not yet defined by the business team. Only "high cti" kind of values are being handled.
            if property_modifier["modifier"]["value"]=="high":
                property_modifier["modifier"]["value"]="plc 0"
        return property_modifier
    
    if len(result["PROPERTY"])>0:
        properties_modifiers = result["PROPERTY"]
        modifier_unit_conversion(properties_modifiers, DEPENDENCIES)

        for property_modifier in properties_modifiers:
            #**************
            ul_sub_prop_terms = ['relative thermal index - mechanical impact (rti imp) (°c)',
                'glow wire flammability index',
                'relative thermal index - mechanical strength (rti str) (°c)',
                'glow wire ignition temperature',
                'relative thermal index - electrical (rti elec) (°c)',
                'relative thermal index',
                'glow wire']  
            if any(item == property_modifier["property_name"] for item in ul_sub_prop_terms):
                property_modifier["property_type"] = "ul_sub_property"

            ul_prop_terms = ['dimensional change',
                        'dielectric strength',
                        'comparative tracking index (cti)',
                        'arc resistance']  
            if any(item == property_modifier["property_name"] for item in ul_prop_terms):
                property_modifier["property_type"] = "ul_property"
            #**************

            if "ul_" in property_modifier["property_type"]:
                cti_terms = ["comparative tracking", "comparative tracking index", "cti", 'comparative tracking index rating', 'comparative tracking rating']
                hai_terms = ["high amp arc ignition", "high amp", "hai", "high current arc", "high current arc ignition", "high arc ignition", "arc ignition", "high ampere arc ignition"]
                hvar_terms = ["high voltage arc resistance to ignition", "hvar"]
                hvtr_terms = ["high voltage arc tracking rate", "hvtr"]
                hwi_terms = ["hot wire ignition", "hot-wire ignition", "hot wire", "hot-wire", "hwi"]
                arc_terms = ["arc resis","arc resistance","arc resistivity","arc resistant"]
                
                if any(item in property_modifier["property_name"] for item in cti_terms):
                    property_modifier = ul_property_value_conversion(property_modifier,cti_value_convertion)
                elif any(item in property_modifier["property_name"] for item in hai_terms):
                    property_modifier = ul_property_value_conversion(property_modifier,hai_value_convertion)
                elif any(item in property_modifier["property_name"] for item in hvar_terms):
                    property_modifier = ul_property_value_conversion(property_modifier,hvar_value_convertion)
                elif any(item in property_modifier["property_name"] for item in hvtr_terms):
                    property_modifier = ul_property_value_conversion(property_modifier,hvtr_value_convertion)
                elif any(item in property_modifier["property_name"] for item in hwi_terms):
                    property_modifier = ul_property_value_conversion(property_modifier,hwi_value_convertion)
                elif any(item in property_modifier["property_name"] for item in arc_terms):
                    property_modifier = ul_property_value_conversion(property_modifier,arc_value_convertion)

                if property_modifier["property_name"]=='dimensional change':
                    try:
                        float(property_modifier['modifier']['value'])
                        float(property_modifier['modifier']['min'])
                        float(property_modifier['modifier']['max'])

                        if str(int(float(property_modifier['modifier']['min']))) in search_query_cleaned and \
                            str(int(float(property_modifier['modifier']['max']))) in search_query_cleaned:
                            print("range found in the query")
                            property_modifier['modifier']['value'] = property_modifier['modifier']['max']
                        else:
                            range_percent = ((float(property_modifier['modifier']['max']) - float(property_modifier['modifier']['value']))/ float(property_modifier['modifier']['value']))*100
                            if 9.9 < range_percent < 10.1:
                                # value is present but not range
                                print(f"value is present but not range. Default {range_percent}%")
                                pass
                            else:
                                # value and range are present
                                print(f"value and range {range_percent}% are present")
                                property_modifier['modifier']['value'] = property_modifier['modifier']['max']
                    except Exception as e:
                        # print(f"in exception: {e}")
                        # not a numerical value
                        pass
            elif property_modifier["property_type"]=='property':
                if not property_modifier["modifier"]['min'] and not property_modifier["modifier"]['max'] and not property_modifier["modifier"]['value']:
                    property_modifier["modifier"]['value']='good'

                if property_modifier["property_name"]=='hardness':
                    if property_modifier["modifier"]['unit']=='a':
                        property_modifier["property_name"]='shore a hardness iso 48-4 / iso 868 15s'
                        property_modifier["modifier"]['unit']=''
                    if property_modifier["modifier"]['unit']=='d':
                        property_modifier["property_name"]='shore d hardness iso 48-4 / iso 868 15s'
                        property_modifier["modifier"]['unit']=''
                elif property_modifier["property_name"]=='bulk density iso 60 (kg/m³)':
                    if any(substring in search_query_cleaned for substring in ['specific gravity','specific-gravity','specificgravity'])\
                            and 'bulk' not in search_query_cleaned:
                        property_modifier["property_name"]='density iso 1183 (kg/m³)'
                elif "water absorption" in property_modifier["property_name"]:
                    property_modifier["property_name"]='absorption'

                # elif property_modifier["property_name"]=='hardness, shore a iso 48-4 / iso 868 15s':
                #     property_modifier["property_name"]='shore a hardness iso 48-4 / iso 868 15s'
                # elif property_modifier["property_name"]=='hardness, shore d iso 48-4 / iso 868 15s':
                #     property_modifier["property_name"]='shore d hardness iso 48-4 / iso 868 15s'

    if len(result["FILLER"])>0: 
        for filler_info in result["FILLER"]:  
            if  'filler_name' in filler_info.keys():
                if 'aramide fiber' in filler_info['filler_name']:
                    filler_info['filler_name'].remove('aramide fiber')
                    filler_info['filler_name'].append('aramid fiber')
                if 'long aramide fiber' in filler_info['filler_name']:
                    filler_info['filler_name'].remove('long aramide fiber')
                    filler_info['filler_name'].append('long aramid fiber')


    
    # result["REGION"] = [] #to be used only till  model is updated with region
    outOfScope = identify_out_of_scope_items(DEPENDENCIES, search_query_cleaned, result, user_type) 

    output = {
        "userInput": {
            "searchQuery": search_query
        },
        "modelOutput": {
            "entities": result,
            "unidentified": "",
            "outOfScope": outOfScope
        },
        "modelVersion": DEPENDENCIES["MODEL_VERSION"],
        "apiVersion": DEPENDENCIES["API_VERSION"]
    }

    for key, value in output['modelOutput']['entities'].items():
        temp = []
        [temp.append(item) for item in value if item not in temp]

        output['modelOutput']['entities'][key] = temp

    return output



