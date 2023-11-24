import os
from pathlib import Path
from typing import Union

import sqlglot
import sqlglot.dialects.bigquery
import sqlglot.dialects.duckdb
import sqlglot.dialects.postgres
from sqlglot import Expression, exp, select
from sqlglot.helper import seq_get

# Apply PSQL monkey patches
from .patches import postgres
from .patches.postgres import DateTime, GenerateArray
# Apply BigQuery monkey patches
from .patches import bigquery

def transpile_query(query: str, source_dialect: str="bigquery", destination_dialect: str="postgres"):
    """
    Transpiles the SQL file from BigQuery to the specified dialect.
    """
    sql_parsed = sqlglot.parse_one(query, read=source_dialect)

    # Remove "physionet-data" as the catalog name
    catalog_to_remove = 'physionet-data'
    for table in sql_parsed.find_all(exp.Table):
        if table.catalog == catalog_to_remove:
            table.args['catalog'] = None
        elif table.this.name.startswith(catalog_to_remove):
            table.args['this'].args['this'] = table.this.name.replace(catalog_to_remove + '.', '')
            # sqlglot wants to output the schema/table as a single quoted identifier
            # so here we remove the quoting
            table.args['this'] = sqlglot.expressions.to_identifier(
                name=table.args['this'].args['this'],
                quoted=False
            )

    if source_dialect == 'bigquery':
        # BigQuery has a few functions which are not in sqlglot, so we have
        # created classes for them, and this loop replaces the anonymous functions
        # with the named functions
        for anon_function in sql_parsed.find_all(exp.Anonymous):
            if anon_function.this == 'DATETIME':
                named_function = DateTime(
                    **anon_function.args,
                )
                anon_function.replace(named_function)
            elif anon_function.this == 'GENERATE_ARRAY':
                named_function = GenerateArray(
                    **anon_function.args,
                )
                anon_function.replace(named_function)

    # convert back to sql
    transpiled_query = sql_parsed.sql(dialect=destination_dialect, pretty=True)
    
    return transpiled_query

def transpile_file(source_file: Union[str, os.PathLike], destination_file: Union[str, os.PathLike], source_dialect: str="bigquery", destination_dialect: str="postgres"):
    """
    Reads an SQL file in from file, transpiles it, and outputs it to file.
    """
    with open(source_file, "r") as read_file:
        sql_query = read_file.read()
    
    transpiled_query = transpile_query(sql_query, source_dialect, destination_dialect)
    # add "create" statement based on the file stem
    transpiled_query = (
        "-- THIS SCRIPT IS AUTOMATICALLY GENERATED. DO NOT EDIT IT DIRECTLY.\n"
        f"DROP TABLE IF EXISTS {Path(source_file).stem}; "
        f"CREATE TABLE {Path(source_file).stem} AS\n"
    ) + transpiled_query

    with open(destination_file, "w") as write_file:
        write_file.write(transpiled_query)

def transpile_folder(source_folder: Union[str, os.PathLike], destination_folder: Union[str, os.PathLike], source_dialect: str="bigquery", destination_dialect: str="postgres"):
    """
    Transpiles each file in the folder from BigQuery to the specified dialect.
    """
    source_folder = Path(source_folder).resolve()
    for filename in source_folder.rglob("*.sql"):
        source_file = filename
        destination_file = Path(destination_folder).resolve() / filename.relative_to(source_folder)
        destination_file.parent.mkdir(parents=True, exist_ok=True)

        transpile_file(source_file, destination_file, source_dialect, destination_dialect)
