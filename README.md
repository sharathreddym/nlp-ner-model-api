# NER for Celanese

This project revolves around the development and implementation of a Named Entity Recognition (NER) model designed to enhance the search experience on Chemille. The primary goal of this project is to identify and extract specific entities from natural language search queries entered by users. These entities play a crucial role in recommending the correct grade to the user, making it easier for users to find relevant grades they are looking for.

The NER model is trained to recognize the following entities:

- GRADE: List of Celanese grades.
- APPLICATION: List of applications.
- BRAND: List of Celanese brands.
- POLYMER: List of polymers.
- PROPERTY: List of property details dictionary, containing name, a modifier dictionary (value, min, max, unit), and property type (property/ul_property/ul_sub_property).
- FILLER: It contains two dictionaries, one containing filler_name list and the other capturing the total_load (value, min, max).
- FEATURE: List of product functions.
- PROCESSING: List of processing types.
- DELIVIERY_FORM: List of delivery forms.
- COMPETITOR_GRADE: List of competitor grades.
- AUTO_CERT: List of dictionaries. Each dictionary captures an OEM and its respective certifications (list).
- RAILWAY_CERT: A dictionary capturing standard, hazard_level (list) and req_set (list).
- WATER_CERT: List of dictionaries. Each dictionary captures standard and temp (certification temperature).
- NSF_CERT: List of NSF certifications.
- INDUSTRY: List of industries.
- REGION: List of regions.

# Anaconda Installation

Download and install [Anaconda](https://www.anaconda.com/download).

# Set HTTPS_PROXY

Set HTTPS_PROXY before installing any conda/python package. Run the command below:

```bash
set HTTPS_PROXY=czgdcsdwankerb1.czds.bz:8080
```

Note: Machines that use VPN or a different network might not need the proxy to install the libraries

# Creating an environment from an environment.yml file (Local)

Open Anaconda prompt and run the command below:

```bash
conda env create -f environment.yml
```

# Activating an environment (Local)

```bash
conda activate gst_ner
```

# Run NER Pipeline in local

onlinescoring.score.py is the main module to run the NER Pipeline.

# NER Dependencies

- **final_unit_conversion_table.**csv****: Unit conversion mapping file for all the general properties where incoming units needs to be mapped with ceed units. Example: GPa to MPa. Used for unit conversion by referring the formula.
- **final_unit_conversion_table_for_exceptions.csv**: Unit conversion mapping file for exceptions such as Tensile modulus tape, Flexural modulus tape, Specific Resistivity, Bulk density, Average particle size, Inclined-plane tracking where incoming units needs to be mapped with ceed units with exceptions. Used for unit conversion by referring the formula only for exceptional properties.
- Abbreviations file: A XLSX file where abbreviations terms are replaced with its meaning.
- **outOfScopeData.json**: Contains out-of-scope data required to segregate the in-scope and out-of-scope entities.
- **normalized_competitor_names.json**: Contains list of competitor names, these are referred to remove the competitor name from the competitor grade. Here the normalized names contains spacing which is an exception case.
- **normalized_unique_values_for_grade_mapping.json:** Contains data that is used in pro-processing / post-processing for pattern matching and validations steps. If any search term needs to be skipped from pre-processing logic, you can add the search term to “columnstoIgnore” and “columnsforSubstringCheck”.
- **oos_color_code_pattern.json**: List of regex patterns referred to remove the color code from the grade.

# Updating NER Dependencies

- Unit conversion files: "**./Development files/Generate Unit Conversion table/Unit conversion tables.ipynb"**

  - **This generates two unit conversion mapping tables**
  - **Update this as and when new units are introduced to the data.**
- Important Notebooks in "./Development files/":

  - ***“1. Clean out of scope Data.ipynb”**: Saves latest **outOfScopeData.json** file in local.*
  - **“2. Create normalized Grade and Competitor Grade names.ipynb”:** Saves latest **normalized_unique_values_for_grade_mapping.json**
    and **normalized_competitor_names.json** file in local.
  - **“3.** **OOS Color codes.ipynb”**: Saves latest **oos_color_code_pattern.json** **file in local.**

# Model Training and Deployment

- **Training Data**: The examples include both real data and generated data:
  - **Real Data**: These data include examples collected from the survey conducted within Celanese, enhancement examples, examples provided by the business team, and sample examples from production queries.
  - **Generated Data**: We use the templates that mimics production queries and additional queries that covers most of the complex business rules.
- Run the notebooks from 1 to 7 ("./Development files/NER_Training/") to generate a fresh set of Generated Data, merge with the Real Data, format and convert them into a training examples for the LLMs. For small changes, skip the first 3 notebooks by reusing the previous generated data.
- **Model**: We use OpenAI's **GPT-4o-Mini** as the base model for finetuning in Azure, where the training data consists of 40-50K training examples and 10-13K of validation examples.
- **Deployment**: We deploy the finetuned model twice in Azure, one for the production (suffixed with "-prod") and the other is for non-production environments. The NER Pipeline uses the deployment name to inference the Model.

# NER Endpoint Deployment

- NER Model pipeline is [deployed](https://ml.azure.com/endpoints/realtime/gst-ner-endpoint/detail?wsid=/subscriptions/710c48d7-7060-4d97-9be0-699f76c25447/resourcegroups/rg-gst-dev-ussc-01/providers/Microsoft.MachineLearningServices/workspaces/ml-gst-dev-usscc-01&tid=7a3c88ff-a5f6-449d-ac6d-e8e3aa508e37) as an Online endpoint in Azure ML Studio.
- **NER-Model-deployment-pipeline-(dev/qa/uat/prod).ipynb** (Notebook) is used for the deployment based on the environment you want to deploy.
- Run the notebook in a Azure ML studio compute instance to do deployment.
- Make sure to pull the latest code from the repo and include the **.env** file in the "onlinescoring/ " folder.
- If any change in the "dependencies/" folder, register the dependencies and update the registered model's (dependencies) version before deploying.

# Best Practices

- API Version: Update the API Version when there is a deployment.
- Update environment.yml (for local)) if any new package is installed and being used.
- Update the "./environment/conda.yml" if any new package is installed and being used.
- Make use of global variables inside the init() function in 'onlinescoring\score.py'.
- Avoid frequent finetuning if the new requirements or a NER issue can be fixed by rule-based approach.

# Debugging and local testing

'onlinescoring/score.py' is the main module and to debug/run the NER pipeline locally, uncomment the code block as shown below:

```python
if __name__ == '__main__':
    init()
    ner_output = run('{"data": "(looking for a material with tensile modulus of 2000 MPa)"}') # update the query
    print(ner_output)
```

