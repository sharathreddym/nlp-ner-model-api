
# Prodigy Setup: 

Open Anaconda prompt and enter the commands below.

## Set HTTPS_PROXY: 

```bash
set HTTPS_PROXY=czgdcsdwankerb1.czds.bz:8080 
```

## Create conda environment:

```bash
conda create -n prodigy python=3.10
```
Proceed ([y]/n)?

Enter: 

```bash
y
```

## Activate conda environment:

```bash
conda activate prodigy
```

## Install prodigy from .whl file (change the path): 

```bash
pip install prodigy -f ./path/prodigy-1.11.13-cp310-cp310-win_amd64.whl
```

## To check if prodigy is installed:

```bash
python -m prodigy stats
```

## Lists all the datasets

```bash
python -m prodigy stats -ls    
```

# Run the prodigy tool for annotation: 

You need to have patterns and query (.jsonl) files as parameters for the command. Use 'Development files\prodigy\2 - Create Patterns File.ipynb' and 'Development files\prodigy\3 - Excel Queries into Prodigy format.ipynb' to create those files.

For more information refer to [prodigy documentation](https://prodi.gy/docs).

Run the command below to open the tool.

```bash
python -m prodigy ner.manual dataset_name blank:en ./path/queries.jsonl --label APPLICATION,BRAND,POLYMER,PROPERTY,MODIFIER,FILLER,FILLER_PERCENTAGE,FEATURE,COMPETITOR_GRADE --patterns ./path/patterns.jsonl
```

Here dataset_name is the name of the dataset where annotated data are saved. We need to change the names below:
- dataset_name
- ./path/queries.jsonl
- ./path/patterns.jsonl

# Review the annotated dataset:

```bash
python -m prodigy review new_dataset_name dataset_name --label BRAND,POLYMER,PROPERTY,FEATURE,FILLER,GRADE,CERTIFICATION,COMPETITOR_GRADE,APPLICATION,MODIFIER,FILLER_PERCENTAGE
```

 We need to change the names below:
- new_dataset_name
- dataset_name

# Export the annotated dataset:

```bash
python -m prodigy db-out dataset_name > ./path/to/annotations.jsonl
```

 We need to change the names below:
- dataset_name
- ./path/to/annotations.jsonl

# Manually review the annotated data

Use the file 'Development files\prodigy\4 - Prodigy labelled data review.ipynb' to create the excel  where you can manually ignore the queries if labels are wrong.
