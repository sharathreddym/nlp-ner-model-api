# dependencies-sample

Miniature copies of every file in `flat-repo-ner/dependencies/`, with the **same schema**
and a handful of **real** rows each, so the structure can be reviewed quickly.

**Do not point the service at this folder** - it is for reading, not running.
Regenerate with `python ../make_dependencies_sample.py`.

Full explanation: [`17-dependencies-files-explained.md`](../17-dependencies-files-explained.md)

| File | Live? | Sample holds |
|---|---|---|
| `unique_values_22_02_24.json` | yes | 5 values per key (16 keys) |
| `chemical_resistance.json` | yes | 3 of 11 categories, 2 sub-categories each |
| `normalized_unique_values_for_grade_mapping.json` | yes | 5 values per key (10 keys) |
| `normalized_competitor_names.json` | yes | 12 of 1,165 names |
| `outOfScopeData.json` | yes | 5 values per key (10 keys) |
| `ul_list_name_value.json` | yes | 3 of 28 UL properties, complete |
| `oos_color_code_pattern.txt` | yes | 6 of 43,667 alternations |
| `final_unit_conversion_table.csv` | yes | 8 of 1,496 rows |
| `final_unit_conversion_table_for_exeptions.csv` | yes | 8 of 286 rows |
| `abbreviations.xlsx` | yes | 8 rows per sheet (4 sheets) |
| `outOfScopeData_new.json` | **no** | 5 per key - the corrected data, not loaded |
| `unique_values_22_02_24_index.json` | **no** | 3 keys x 3 values |
| `unique_values_22_02_24_preprocessed.json` | **no** | 3 keys x 3 values |
| `model-best/` | **no** | empty in the real repo too |
| `.amlignore` | n/a | copied verbatim |
