import re
import json
import string
import copy

GRADE_OFFSET_TERMS = ["imds", "tds", "sds", "alternatives", "alternative", "alternate", "similar", "offset",  "replacement", "replace", "replacing", "in place", "inplace", "instead", "of", "for", "to", "find", "search", "searching", "look", "looking", "i", "want", "show", "me", "an", "a","grades", "grade", "material", "materials", "competitor", "competitors", "specs", "spec", "specification", "specifications"]

def add_spaces(text, values, units) -> str:
    """
    Adds appropriate spacing around special characters in text while preserving specific values and units.

    This function processes text to ensure proper spacing around special characters like hyphens and dots,
    while being careful not to modify values and units that should remain intact. It's particularly useful
    for text readability in search queries.

    Parameters:
        text (str): The input text string to be processed
        values (list): A list of special values/terms that should be preserved without modification
        units (list): A list of measurement units that should be preserved without modification

    Returns:
        str: The processed text with appropriate spacing added around special characters, while
             preserving specified values and units

    Logic:
        1. Splits input text into words
        2. For each word:
           - If word is found in values/units lists or is a substring, keeps it unchanged
           - Otherwise:
             - Adds spaces around hyphens between numbers and non-numbers
             - Preserves scientific notation (e.g., '10^-6', 'e-6')
             - Adds spaces after dots between letters/numbers
        3. Joins processed words back together
        4. Cleans up any extra whitespace
        5. Preserves special cases like '+/- for range scenarios'
    """

    words = text.split()
    updated_words = []
    for word in words:
        #         if any(word.startswith(v) for v in values):
        if any(word in v for v in values) or any(word[1:] in v for v in values) or any(word[:-1] in v for v in values) or \
                any(word.endswith(v) for v in units) or any(word[:-1].endswith(v) for v in units):
            # Word is substring in one of the lists, add word
            #             print(word)
            updated_words.append(word)
        else:
            # processed_word = word.replace("/", " / ")  # .replace("-", " -")
            pattern = r"(?<=\D)-(?=\d)|(?<=\d)-(?=\D)|(?<=\D)-(?=\D)"
            processed_word = re.sub(pattern, ' - ', word)
            # 9.0x10^ -6 >>>>>>>>>> 9.0x10^-6
            processed_word = re.sub(
                r"(?<=\d)\^ - (?=\d)", '^-', processed_word)
            # 9.0e -6 >>>>>>>> 9.0e-6
            processed_word = re.sub(r"(?<=\d)e - (?=\d)", 'e-', processed_word)
            dot_pattern = r'(?<=[a-zA-Z])\.(?=[a-zA-Z])|(?<=[a-zA-Z])\.(?=\d)|(?<=\d)\.(?=[a-zA-Z])'
            processed_word = re.sub(dot_pattern, '. ', processed_word)
            updated_words.append(processed_word)

    cleaned_text = " ".join(updated_words)
    cleaned_text = re.sub("(\s+)", " ", cleaned_text.strip())
    cleaned_text = cleaned_text.replace("+/ -", "+/-")
    return cleaned_text


# Trim all the enities
def remove_brackets(labelled_text) -> str:
    """
    Removes brackets from the input text while preserving the content within them.

    This function processes text to remove all types of brackets (parentheses, square brackets, and curly braces)
    while preserving the content within them. It ensures that the text is cleaned of any unnecessary brackets,
    making it easier to process and analyze.

    Parameters:
        labelled_text (str): The input text string to be processed

    Returns:
        str: The processed text with all brackets removed, preserving the content within them
    """

    for i in [("(", ")"), ("[", "]"), ("{", "}")]:
        if i[0] in labelled_text and not i[1] in labelled_text:
            labelled_text = labelled_text.replace(i[0], " ")
        elif i[1] in labelled_text and not i[0] in labelled_text:
            labelled_text = labelled_text.replace(i[1], " ")

    if labelled_text:
        for i in [("(", ")"), ("[", "]"), ("{", "}"), ("'", "'"), ('"', '"')]:
            if i[0] == labelled_text[0] and i[1] == labelled_text[-1]:
                labelled_text = labelled_text[1:-1]
                break

    return labelled_text


def remove_unwanted_characters(labelled_text) -> str:
    """
    Removes unwanted characters from the input text while preserving the content within them.

    This function processes text to remove specific characters that are not typically used in search queries.
    It ensures that the text is cleaned of any unnecessary characters, making it easier to process and analyze.

    Parameters:
        labelled_text (str): The input text string to be processed

    Returns:
        str: The processed text with all unwanted characters removed
    """

    trim_characters = ["=", "/", "-", ",", ":",
                       ";", "#", "$", "&", "*", "?", "|", "@"]
    if labelled_text and len(labelled_text) > 1 and labelled_text[0] in trim_characters and not labelled_text[1:].split()[0][0].isnumeric():  # or
        labelled_text = labelled_text[1:]

    if labelled_text and labelled_text[-1] in trim_characters:
        labelled_text = labelled_text[:-1]
    return labelled_text.strip()


def remove_hyphens(labelled_text) -> str:
    """
    Removes hyphens from the input text while preserving the content within them.

    This function processes text to remove hyphens while preserving the content within them.
    It ensures that the text is cleaned of any unnecessary hyphens, making it easier to process and analyze.

    Parameters:
        labelled_text (str): The input text string to be processed

    Returns:
        str: The processed text with all hyphens removed, preserving the content within them

    Note: 
        - converts "- -" to "-" (e.g. this can occur after removing unwanted characters) 
    """

    # converts "- -" to "-"
    labelled_text = re.sub(r'(- ){2,}', r'-', labelled_text)
    pattern = r'^(-+)(?![-.\d])|(?<![-.\d])(-+)$'
    labelled_text = re.sub(pattern, '', labelled_text)
    labelled_text = re.sub("(\s+)", " ", labelled_text.strip())
    return labelled_text


def trim(labelled_text) -> str:
    """
    Recursively trims and cleans text by removing unwanted characters, brackets, and hyphens.

    This function acts as a wrapper that coordinates multiple text cleaning operations, applying them
    recursively until no further changes can be made to the text. It ensures thorough cleaning by
    repeatedly processing the text until it reaches a stable state.

    Parameters:
        labelled_text (str): The input text string to be cleaned and trimmed

    Returns:
        str: The fully cleaned and trimmed text after all processing is complete

    Logic:
        1. Stores original text length for comparison
        2. Removes brackets via remove_brackets()
        3. Removes hyphens ("- -") via remove_hyphens() 
        4. Removes other unwanted characters via remove_unwanted_characters()
        5. If text length changed during processing, recursively calls itself
           to ensure all possible cleaning is performed
        6. Returns final cleaned text once no further changes occur
    """

    labelled_text_len = len(labelled_text)
    cleaned_labelled_text = remove_brackets(labelled_text)

    cleaned_labelled_text = remove_hyphens(cleaned_labelled_text)

    cleaned_labelled_text = remove_unwanted_characters(cleaned_labelled_text)

    if len(cleaned_labelled_text) == labelled_text_len:
        return cleaned_labelled_text
    else:
        return trim(cleaned_labelled_text)

def convert_property_shortforms_with_values(labelled_text) -> str:
    """
    Converts property shortforms with values to their full text representation.

    This function processes text to identify and replace property shortforms with their full text equivalents.
    It ensures that the text is standardized by converting common shorthand notations into their full forms.

    Parameters:
        labelled_text (str): The input text string to be processed

    Returns:
        str: The processed text with property shortforms replaced by their full text equivalents

    Note:
        - Converts sg1.4, hdt200 to proper format like "sg of 1.4", "hdt of 200".
        - This is a very specific function and should be used only for property/UL shortforms with values which can be confusing with fillers like "gf30", "cd10" etc.
    """

    pattern = r"\d+\.\d+sg|sg\d+\.\d+|\d+sg|sg\d+|\d+\.\d+hdt|hdt\d+\.\d+|\d+hdt|hdt\d+"
    matches = re.findall(pattern, labelled_text)
    for match in matches:
        numbers = re.findall(r'[0-9.]+', match)
        text = re.findall(r'[a-z]+', match)
        labelled_text = labelled_text.replace(match, f"{text[0]} of {numbers[0]}", 1)
    return  labelled_text

def normalize_query(s):
    """
    Normalizes the input text by removing special characters, retaining only alphanumeric characters and converting it to lowercase.

    This function supports grade/competitor_grade/auto_certification pattern matching.

    Parameters:
        s (str): The input text string to be processed

    Returns:
        str: The processed text with only alphanumeric characters and in lowercase
    """
    # remove additional words like offset, replacement
    s = s.lower().split()
    s = " ".join([substring for substring in s if substring not in GRADE_OFFSET_TERMS])
            
    # Remove special characters and convert to lower case
    return re.sub(r'\W+', '', s)


def data_preprocessing(text, values, units, DEPENDENCIES) -> str:
    """
    Performs comprehensive preprocessing on input text to standardize and clean it for NER extraction.
    
    This function applies a series of text preprocessing steps to clean search queries,
    including handling special characters, adding appropriate spacing and text formatting. It is also used for normalizing
    the text for grade/competitor_grade/auto_certification pattern matching.

    Parameters:
        text (str): The raw input text/search query to be preprocessed
        values (list): List of values/terms that should be preserved during preprocessing
        units (list): List of property/UL units that should be preserved during preprocessing 
        DEPENDENCIES (dict): Dictionary containing configuration and dependencies needed for preprocessing (currently not used)

    Returns:
        tuple: 
        - The preprocessed text (for NER extraction)
        - Normalized text (for grade/competitor_grade/auto_certification pattern matching).

    Logic:
        1. Removes/replaces special characters ($, #, :, ®, ™)
        2. Standardizes separators and comparison operators
        3. Removes extra whitespace
        4. Standardizes formats for operators (<, >, =)
        5. Adds appropriate spacing around operators and special characters
        6. Preserves numeric values and units based on provided lists
        7. Converts temperature formats ('˚c', '℃) to standard '°C'
        8. Handles special cases like <=, >=, !=
        9. Converts property abbreviation with value "HDT20" to property value template format ("{PROPERTY_NAME} of {VALUE}") to avoid confusion with fillers ("GF20")
        10. Converts "performance level category" to "plc" (was impactful for spacy model)
        11. Standardizes eco terms.
        12. Normalizes the search query for grade/competitor_grade/auto_certification pattern matching
    """
    query = copy.deepcopy(text)
    # remove $, #, :
    query = query.replace('$', ' ').replace('#', ' ').replace(":", ' ').replace("®", '').replace("™", '')
    # replace 
    query = query.replace(";", ", ").replace("；", ", ").replace("~", '- ').replace("–", "-")
    query = query.replace("≠", "!=").replace("≤", "<=").replace("≥", '>=')
    
    # remove extra spaces
    query = re.sub("(\s+)", " ", query.strip())

    # trim
    query = trim(query)

    # replace multiple occurance with single occurance
    query = re.sub(r'[!@%?\'=&\.]+', lambda match: match.group(0)[0], query)
    query = re.sub(r'[,]+', lambda match: match.group(0)[0], query)

    # replace special characters to right format
    query = query.replace('（', "(").replace('）', ')').replace('ºc', "°c").replace(
        '˚c', "°c").replace('℃', "°c").replace('=<', "<=").replace('=>', '>=').lower()

    # find all occurrences of the pattern and add a space after each match
    pattern1 = r'(?<=[<>=!])(?=[^=])|(?<=[^<>=])(?=[<>=!])'
    query = re.sub(pattern1, ' ', query).replace("! =", "!=")

    # add space before and after for "+" "@" "|" "&"
    # we can include more characters inside the [] like r'([+,/-])'
    query = re.sub(r'([:&+@|()\[\]\{\}])', r' \1 ', query)

    # add space after for ";", ":" "?" "%" ")"
    query = re.sub(r'([;?%])', r'\1 ', query)

    # add space after for ","
    pattern2 = r"(?<=\D),(?=\d)|(?<=\d),(?=\D)|(?<=\D),(?=\D)"
    query = re.sub(pattern2, ', ', query)

    # after adding spaces, we are removing if any multiple spaces exist
    query = re.sub("(\s+)", " ", query.strip())

    # remove unnecessary spaces
    query = query.replace("+ /", "+/")

    # converting some cases to right format
    # replace("<= >=", "<==>").
    query = query.replace("> / =", ">=").replace("< / =", "<=").replace(
        "= / >", ">=").replace("= / <", "<=").replace("< >=", "<=>")

    # add space for ".", "/", "-"
    query = add_spaces(query, values, units)

    #convert sg1.4, hdt200 to proper format
    query = convert_property_shortforms_with_values(query)

    query = query.replace("performance level category", "plc")
    ecor_pattern = r'eco\s*[\-\/\s]?\s*r\b'
    ecob_pattern = r'eco\s*[\-\/\s]?\s*b\b'
    ecoc_pattern = r'eco\s*[\-\/\s]?\s*c\b'
    query = re.sub(ecor_pattern, 'eco-r', query)
    query = re.sub(ecob_pattern, 'eco-b', query)
    query = re.sub(ecoc_pattern, 'eco-c', query)

    # remove extra spaces (do always just before return)
    query = re.sub("(\s+)", " ", query.strip())
    query_for_grade_match = normalize_query(query)

    #convert kepital brand search to celcon brand search
    pattern = re.compile(r'\b(kepital|kep)\b', re.IGNORECASE)
    if re.search(pattern, query):
        replacement = "celcon"
        query_with_replacement = re.sub(pattern, replacement, text)
        query = query_with_replacement

    #convert different variations of 'auto injector' to 'auto-injector'
    auto_injector_forms = ["auto-injector", "auto injector", "auto_injector", "autoinjector"]

    if query in auto_injector_forms:
        query = "auto-injector"

    #handle competitor grade brand names with 'spaces'
    #handle applications' abbreviations for e&e DAS role out
    replacements = {
       'tenac c': 'tenac-c',
       'hi zex': 'hi-zex',
       'el lene': 'el-lene', 
       'hi prene':'hi-prene', 
       'dic pps': 'dic-pps', 
       'fil a gehr': 'fil-a-gehr', 
       'gravi tech': 'gravi-tech', 
       'neo zex': 'neo-zex',
       'cool poly': 'coolpoly',
       'hsd': 'high speed data',
       'w & c': 'wire & cable',
       'labs': 'lead acid battery separator',
       'ff': 'full frame'
       #'wtb': 'wire to board'
    }

    for key in replacements:
        if key in query:
            pattern = r'\b' + re.escape(key) + r'\b'
            query = re.sub(pattern, replacements[key], query)
            #query = query.replace(key, replacements[key])

    return query, query_for_grade_match

