import logging
from collections import defaultdict

import pandas as pd


def _recursive_geometric_union_of_series(shape_series):
    """Recursively dissolve series of Geometry objects into a single Geometry using Geometry.union()

    Args:
        shape_series (pd.Series): A series of arcgis.geometry.Geometry objects

    Returns:
        arcgis.geometry.Geometry: The geometric union of all the Geometries.
    """

    if shape_series.size == 2:
        return shape_series.iloc[0].union(shape_series.iloc[1])
    else:
        return shape_series.iloc[0].union(_recursive_geometric_union_of_series(shape_series.iloc[1:]))


def _dissolve_geometries(duplicates_df, dissolve_field):
    """Dissolve all sets of geometries associated with duplicate dissolve_field values into one geometry per value

    Args:
        duplicates_df (pd.DataFrame): Spatial data frame containing a non-unique field of values and their associated shapes
        dissolve_field (str): The field containing duplicated values associated with unique shapes.

    Returns:
        pd.DataFrame: A dataframe containing each unique value in dissolve_field and it's associated dissolved geometry.
    """

    grouped = duplicates_df.groupby(dissolve_field)
    dissolved_geometries_series = grouped['SHAPE'].agg(_recursive_geometric_union_of_series)
    dissolved_geometries_df = pd.DataFrame({
        dissolve_field: dissolved_geometries_series.index,
        'SHAPE': dissolved_geometries_series.values
    })

    return dissolved_geometries_df


def _dissolve_attributes(duplicates_df, dissolve_field, fields_map):

    #: Count, First, sum, max

    ops_and_fields = _group_common_field_ops(fields_map)
    for op, fields in ops_and_fields.items():
        if op == 'count':


def _group_common_field_ops(fields_map):

    ops_and_fields = defaultdict(list)
    for field, op in fields_map.items():
        ops_and_fields[op.casefold()].append(field)

    return ops_and_fields





def _combine_geometries_and_attributes(geometries_df, attributes_df, dissolve_field):
    """Combine dissolved geometries and attributes into a single dataframe based on the values in dissolve_field

    Args:
        geometries_df (pd.DataFrame): Spatial dataframe containing dissolve_field and dissolved geometries
        attributes_df (pd.DataFrame): Dataframe containing dissolve_field and aggregated/transformed attributes
        dissolve_field (str): Common field the geometries and attributes were dissolved on

    Raises:
        ValueError: If values in dissolve_field are not unique in both dataframes (ie, validates 1:1 merge)

    Returns:
        pd.DataFrame: Dataframe merged on dissolved_field containing all fields in geometries_df and attributes_df
    """

    return attributes_df.merge(geometries_df, on=dissolve_field, how='outer', validate='1:1')


def _recombine_dissolved_with_all(dissolved_combined, uniques):
    """Append dissolved dataframe with original uniques for one cohesive dataset with all unique values

    Args:
        dissolved_combined (pd.Dataframe): Spatial dataframe with all non-unique dissolve field rows dissolved into single rows.
        uniques (pd.DataFrame): All unique dissolve field rows from original spatial dataframe

    Returns:
        pd.DataFrame: Combination of rows from dissolved dataframe and uniques dataframe.
    """

    return pd.concat([dissolved_combined, uniques], ignore_index=True)


def _extract_duplicates_and_uniques(dataframe, dissolve_field):
    """Divide a dataframe into rows with non-unique dissolve_field values and rows with unique dissolve_field values.

    Args:
        dataframe (pd.DataFrame): Dataframe to divide based on values in dissolve_field
        dissolve_field (str): Name of column holding values to determine uniqueness

    Raises:
        RuntimeError: If the number of unique rows and number of non-unique rows don't sum to the original number of
        rows (would really love to hear if this ever gets raised)

    Returns:
        tuple(pd.DataFrame): Dataframe of duplicate rows, dataframe of unique rows
    """

    duplicates = dataframe[dataframe[dissolve_field].duplicated(keep=False)].copy()
    uniques = dataframe[~(dataframe[dissolve_field].duplicated(keep=False))].copy()

    original_length = dataframe.shape[0]
    duplicates_length = duplicates.shape[0]
    uniques_length = uniques.shape[0]
    logging.debug(f'{original_length} original rows, {duplicates_length} duplicates and {uniques_length} uniques')

    if duplicates_length + uniques_length != original_length:
        raise RuntimeError("Duplicates plus uniques don't equal original.")

    return duplicates, uniques


def dissolve_duplicates_by_dataframe(dataframe, dissolve_field, fields_map):
    duplicates, uniques = _extract_duplicates_and_uniques(dataframe, dissolve_field)

    dissolved_geometries = _dissolve_geometries(duplicates, dissolve_field)
    dissolved_attributes = _dissolve_attributes(duplicates, dissolve_field, fields_map)

    dissolved_combined = _combine_geometries_and_attributes(dissolved_geometries, dissolved_attributes, dissolve_field)

    all_combined = _recombine_dissolved_with_all(uniques, dissolved_combined)

    return all_combined
