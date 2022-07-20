import logging
import warnings
from datetime import datetime

import arcpy
import numpy as np
import pandas as pd

from housing_unit_inventory import dissolve


def get_proper_built_yr_value_series(parcels_df, index_col, built_yr_col):
    """Return the largest most common yearbuilt value for each group or the largest value if the most common is 0

    Returns the mode of the yearbuilt value (taking the largest value if there are multiple modes). If the mode is 0,
    it returns the largest yearbuilt value instead (ie, for one or two built units and many more under construction,
    you will get the latest year from the built units).

    Args:
        parcels_df (pd.DataFrame.spatial): The parcels data
        index_col (str): The column to group the parcels by
        built_yr_col (str): The column holding the built year as an integer/float

    Returns:
        pd.Series: A series of the built year, indexed by the unique values in index_col
    """

    parcels_grouped = parcels_df.groupby(index_col)

    #: Using .agg(pd.Series.mode) has inconsistent behavior based on whether the first group returns a single mode
    #: or multiple modes, so using .apply instead: https://github.com/pandas-dev/pandas/issues/25581
    built_yr_mode_series = parcels_grouped[built_yr_col].apply(pd.Series.mode)

    #: If there are multiple modes, we just get the largest by flattening the index into a df and doing another groupby
    if isinstance(built_yr_mode_series.index, pd.MultiIndex):
        built_yr_mode_series = (
            pd.DataFrame(built_yr_mode_series) \
                .reset_index() \
                .groupby(index_col)[built_yr_col].max()
        )

    built_yr_max_series = parcels_grouped[built_yr_col].max()
    built_yr_df = pd.DataFrame({'mode': built_yr_mode_series, 'max': built_yr_max_series})
    built_yr_df[built_yr_col] = built_yr_df['mode']
    built_yr_df.loc[built_yr_df[built_yr_col] <= 0, built_yr_col] = built_yr_df['max']

    return built_yr_df[built_yr_col]


#: Unused
def change_geometry(dataframe, to_new_geometry_column, current_geometry_name):
    """Swap between spatially-enabled data frame shape columns.

    Copies new column to 'SHAPE' and resets the geometry and spatial index to support operations that expect the
    geometry column to be 'SHAPE'. Saves the existing 'SHAPE' data to a new column so that you can swap back later.
    Edits the dataframe in place, does not create a new copy.

    Args:
        dataframe (spatially enabled DataFrame): The dataframe to swap geometries. Should have an existing 'SHAPE'
        geometry column.
        to_new_geometry_column (str): The the new column in df to use for geometry. Will be copied over to 'SHAPE'.
        current_geometry_name (str): A name for the column to copy the existing 'SHAPE' column to for future reuse.
    """
    #: WARNING: if you do this twice with the same geometry, you may overwrite the other column and lose it forever.
    #: I haven't tested that yet.

    dataframe[current_geometry_name] = dataframe['SHAPE']
    dataframe['SHAPE'] = dataframe[to_new_geometry_column]
    dataframe.spatial.set_geometry('SHAPE')
    dataframe.spatial.sindex(reset=True)  #: not sure how necessary this is, but for safety's sake


def add_extra_info_from_csv(info_csv, pad_length, csv_fields, parcels_df, csv_join_field_type=str):
    """Add extra info from a csv, joining onto parcel's PARCEL_ID

    Args:
        info_csv (str): Path to csv holding extra info
        pad_length (int): Width to pad the csv's join field with 0's to match the parcel's PARCEL_ID
        csv_fields (List<str>): List of fields from the csv to include in the join. The first field in the list will be used as the join field against the parcels' PARCEL_ID.
        parcels_df (pd.DataFrame): Parcels dataset with a PARCEL_ID column
        csv_join_field_type (Type, optional): Type the csv's join field should be set. Defaults to str.

    Raises:
        ValueError: If values in the csv's join column are not unique (raised from pandas' merge validate='m:1' check)

    Returns:
        pd.DataFrame: Parcels dataset with info from csv merged in.
    """

    csv_join_field = csv_fields[0]
    csv_df = pd.read_csv(info_csv, dtype={csv_join_field: csv_join_field_type})

    csv_df[csv_join_field] = csv_df[csv_join_field].str.zfill(pad_length)

    csv_df.dropna(subset=[csv_join_field], inplace=True)

    try:
        parcels_merged_df = parcels_df.merge(
            csv_df[csv_fields], left_on='PARCEL_ID', right_on=csv_join_field, how='left', validate='m:1'
        )
    except pd.errors.MergeError as error:
        raise ValueError(f'Values in csv join field {csv_join_field} are not unique.') from error

    return parcels_merged_df


def get_centroids_copy_of_polygon_df(polygon_df, join_field):
    """Get the centroids of a polygon dataframe by round-tripping through FeatureToPoint, using INSIDE parameter

    Args:
        polygon_df (pd.DataFrame.spatial): Dataframe to get the centroids of (guaranteed to be inside the polygons)
        join_field (str): Unique id field in polygon_df for joining data derived from centroids back to the polygons

    Returns:
        pd.DataFrame.spatial: Dataframe containing just the centroids and the common join field.
    """

    memory_parcels = 'memory/parcels'
    memory_centroids = 'memory/centroids'

    for featureclass in [memory_centroids, memory_parcels]:
        if arcpy.Exists(featureclass):
            arcpy.management.Delete(featureclass)

    polygon_df.spatial.to_featureclass(memory_parcels)
    arcpy.management.FeatureToPoint(memory_parcels, memory_centroids, 'INSIDE')
    centroids_df = pd.DataFrame.spatial.from_featureclass(memory_centroids)

    centroids_df.rename(columns={join_field.lower(): join_field}, inplace=True)  #: feature class lowercases the columns

    #: Ensure the join_field type remains the same, round tripping through arcpy may change it
    source_type = polygon_df[join_field].dtype
    centroids_df[join_field] = centroids_df[join_field].astype(source_type)

    blank_centroids = centroids_df['SHAPE'].isna().sum()
    if blank_centroids:
        print(f'{blank_centroids} blank centroids!')

    return centroids_df[[join_field, 'SHAPE']].copy()


def load_and_clean_parcels(parcels_fc):
    """Load parcel feature class, dissolve on PARCEL_ID, remove empty geometries

    Args:
        parcels_fc (pathlib.Path): Path to parcel feature class

    Returns:
        pd.DataFrame: Spatial data frame of de-duplicated, cleaned parcels
    """
    #: TODO: Get parcel_count from this dissolve to document any joins (for checking if other values besides PARCEL_ID
    #: are duplicated.)

    parcels_df = pd.DataFrame.spatial.from_featureclass(parcels_fc)

    field_map = {
        'PARCEL_ID': 'COUNT',
        'TAXEXEMPT_TYPE': 'FIRST',
        'TOTAL_MKT_VALUE': 'SUM',
        'LAND_MKT_VALUE': 'SUM',
        'PARCEL_ACRES': 'SUM',
        'PROP_CLASS': 'FIRST',
        'PRIMARY_RES': 'FIRST',
        'HOUSE_CNT': 'MAX',
        'BLDG_SQFT': 'SUM',
        'FLOORS_CNT': 'MAX',
        'BUILT_YR': 'FIRST',
        'EFFBUILT_YR': 'FIRST',
    }

    dupe_test_fields = list(field_map.keys())

    parcels_dissolved_df = dissolve.dissolve_duplicates_by_dataframe(
        parcels_df, 'PARCEL_ID', field_map, dupe_test_fields
    )

    #: Remove parcels without parcel ids and empty geometries
    parcels_dissolved_df.dropna(subset=['PARCEL_ID', 'SHAPE'], inplace=True)

    #: Ensure HOUSE_CNT is a float (for later comparison and handling NaNs)
    parcels_dissolved_df['HOUSE_CNT'] = parcels_dissolved_df['HOUSE_CNT'].astype(float)

    return parcels_dissolved_df


#: FIXME: May not be needed (see load_and_clean_parcels())
def clean_dissolve_field_names(field_names, prefixes):
    """Remove statistic name (SUM_, etc) from field names from dissolved feature class

    Args:
        field_names (List<str>): Field names from a dissolved feature class
        prefixes (List<str>): Statistic prefixes (SUM_, FIRST_, etc) to remove from field_names

    Returns:
        Dict: Mapping of original names t
    """

    cleaned_names = {}
    for name_with_stat in field_names:
        prefix, _, original_field_name = name_with_stat.partition('_')
        if prefix in prefixes:
            cleaned_names[name_with_stat] = original_field_name

    return cleaned_names


def get_non_base_addr_points(address_pts_fc, type_column_name='PtType', base_address_value='BASE ADDRESS'):
    """Get address points that aren't a base address (ie, main, non-unit address for an apartment building)

    Args:
        address_pts_fc (str): Address point feature class
        type_column_name (str, optional): Field that defines the points' types. Defaults to 'PtType'.
        base_address_value (str, optional): The value indicating a base address. Defaults to 'BASE ADDRESS'.

    Returns:
        pd.DataFrame.spatial: A spatial dataframe without any base addresses
    """

    address_pts_no_base_df = (
        pd.DataFrame.spatial.from_featureclass(address_pts_fc) \
        .query(f'{type_column_name} != @base_address_value')
        )
    return address_pts_no_base_df


def set_common_area_types(evaluated_df):
    """Set TYPE and SUBTYPE values for common unit areas/owned unit groupings

    Args:
        evaluated_df (pd.DataFrame): The fully-evaluated common area parcel dataframe

    Returns:
        pd.DataFrame: The modified and updated evaluated_df
    """

    #: FIXME: we should do this rename when we first load the common areas so that we've got a defined interface
    evaluated_df.rename(columns={
        'TYPE_WFRC': 'TYPE',
        'SUBTYPE_WFRC': 'SUBTYPE',
    }, inplace=True)

    evaluated_df.loc[evaluated_df['SUBTYPE'] == 'pud', 'TYPE'] = 'single_family'

    return evaluated_df


#: FIXME: Davis specific, also sets some vital fields that should probably be done elsewhere so that they can be reused #: for other counties.
def subset_owned_unit_groupings_from_common_areas(
    common_areas_fc, common_area_key_column_name, unique_key_column='OBJECTID'
):
    """Get PUDs and multi-family parcels from common_areas_fc as a dataframe

    Also set IS_OUG to 'Yes' and copy unique_eky_column to to common_area_key_column_name.

    Args:
        common_areas_fc (str): Path to the common areas featureclass.
        common_area_key_column_name: Name of column to be created to hold the unique key for each common area.
        unique_key_column (str, optional): Column holding unique identifier for common areas. Defaults to 'OBJECTID'.
            Will be copied to new common_area_column_name column.

    Raises:
        ValueError: If values in unique_key_column are not unique. Because this column is used later to aggregate
            parcel information, non-unique values will result in improper aggregation and invalid results.

    Returns:
        pd.DataFrame.spatial: Spatially enabled dataframe of owned unit groupings
    """

    common_areas_df = pd.DataFrame.spatial.from_featureclass(common_areas_fc)
    if not common_areas_df[unique_key_column].is_unique:
        raise ValueError(f'Unique key column {unique_key_column} does not contain unique values.')

    #: Warn if common areas contain empty geometries, then drop the appropriate rows.
    empty_shape_row_count = common_areas_df[common_areas_df['SHAPE'].isna()][unique_key_column].count()
    if empty_shape_row_count:
        warnings.warn(f'{empty_shape_row_count} common area row[s] had empty geometries')
        common_areas_df.dropna(subset=['SHAPE'], inplace=True)

    common_areas_df[common_area_key_column_name] = common_areas_df[unique_key_column]

    common_areas_subset_df = common_areas_df[(common_areas_df['SUBTYPE_WFRC'] == 'pud') |
                                             (common_areas_df['TYPE_WFRC'] == 'multi_family')].copy()
    common_areas_subset_df['IS_OUG'] = 'Yes'

    return common_areas_subset_df


#: FIXME: This may be Davis-specific, also the decision to force tri/quad to apartment is hidden in this
def set_multi_family_single_parcel_subtypes(evaluated_df):
    #: SUBTYPE = class unless class == 'triplex-quadplex', in which case it becomes 'apartment' and NOTE becomes tri-quad

    evaluated_df['SUBTYPE'] = np.where(
        evaluated_df['parcel_type'] != 'triplex-quadplex', evaluated_df['parcel_type'], 'apartment'
    )
    evaluated_df['NOTE'] = np.where(evaluated_df['parcel_type'] != 'triplex-quadplex', '', evaluated_df['parcel_type'])

    return evaluated_df


def get_address_point_count_series(areas_df, address_points_df, key_col):
    """Add number of intersecting address points as the UNIT_COUNT

    Args:
        areas_df (pd.DataFrame.spatial): The area geometries
        address_points_df (pd.DataFrame.spatial): Address point dataset with base addresses filtered out
        key_col (str): A column in areas_df that identifies the joined rows that belong to a single source geometry

    Returns:
        pd.Series: The count of addresses, named 'UNIT_COUNT' and indexed by key_col
    """

    address_count_series = (
        areas_df.spatial.join(address_points_df, 'left', 'contains') \
        .groupby(key_col)['SHAPE'].count() \
        .rename('UNIT_COUNT')
    )

    return address_count_series


def standardize_fields(parcels_df, field_mapping):
    """Rename county-specific fields to standardized names based on field_mapping

    Args:
        parcels_df (pd.DataFrame.spatial): Dataframe of parcels with county-specific names
        field_mapping (dict): Mapping of county-specific field names to standardized names ({'account_no': 'PARCEL_ID'})

    Raises:
        ValueError: If a county-specific field name from field_mapping is not found in parcels_df.columns

    Returns:
        pd.DataFrame.spatial: Parcels dataframe with renamed fields
    """

    for original_name in field_mapping.keys():
        if original_name not in parcels_df.columns:
            raise ValueError(f'Field {original_name} not found in parcels dataset.')

    renamed_df = parcels_df.rename(columns=field_mapping)

    return renamed_df


def concat_evaluated_dataframes(dataframes, new_index='PARCEL_ID'):
    """Concatenate dataframes along the index and reset the index to new_index

    Args:
        dataframes (List<pd.DataFrame>): Dataframes to concatenate
        new_index (str, optional): Column to uses as new Index. Defaults to 'PARCEL_ID'.

    Raises:
        ValueError: If the keys in new_index are not unique

    Returns:
        pd.DataFrame: Concatenated, reindexed dataframe
    """

    #: FIXME: reset index, reimplement validation (maybe custom validation check?)
    concated_dataframes = pd.concat(dataframes)  #.set_index(new_index, verify_integrity=True)

    return concated_dataframes


def classify_from_area(parcels_df, parcel_centroids_df, parcel_key, area_df, classify_info=()):
    """Add information from area polygons and/or provided values to parcels whose centroids are in the areas

    Args:
        parcels_df (pd.DataFrame.spatial): Spatial dataframe of parcels (original polygon geometry)
        parcel_centroids_df (pd.DataFrame.spatial): Dataframe of parcel centroids and a unique key
        parcel_key (str): Name of common key column between normal parcels and centroids
        area_df (pd.DataFrame.spatial): Areas dataframe to classify the parcels against
        classify_info (tuple, optional): Tuple of (areas unique key column, target column, value) for optionally manually setting a column value for intersecting parcels. Defaults to ().

    Raises:
        ValueError: If all three required classify_info values are not provided.
        UserWarning: If duplicate parcel keys are found in the spatial join, indicating a centroid is within more than one area. Check for overlapping areas (assumes areas are spatially exclusive).

    Returns:
        pd.DataFrame.spatial: Original parcels_df with info from areas that contain the parcels' corresponding centroids
    """

    if area_df.spatial.sr['wkid'] != parcel_centroids_df.spatial.sr['wkid']:
        logging.debug(f'Reprojecting areas to {parcel_centroids_df.spatial.sr["wkid"]}...')
        if not area_df.spatial.project(parcel_centroids_df.spatial.sr['wkid']):
            raise RuntimeError(f'Reprojecting area_df to {parcel_centroids_df.spatial.sr["wkid"]} did not succeed.')

    #: get only the centroids within the areas
    joined_centroids_df = parcel_centroids_df.spatial.join(area_df, 'inner', 'within')

    dup_parcel_ids = joined_centroids_df[joined_centroids_df.duplicated(subset=[parcel_key], keep=False)]
    if dup_parcel_ids.shape[0]:
        warnings.warn(
            f'{dup_parcel_ids.shape[0]} duplicate keys found in spatial join; check areas features for overlaps'
        )

    #: Remove SHAPE so we can join it to parcels w/o multiple geometry fields, index_right for cleanliness
    joined_centroids_df.drop(columns=['SHAPE', 'index_right'], inplace=True)

    #: Join intersecting centroids back to original parcels, keeping all original
    merged_parcels = pd.merge(parcels_df, joined_centroids_df, how='left', on=parcel_key)

    if classify_info:
        #: Make sure we've got all the necessary classification info
        try:
            areas_unique_key_column, classify_column, classify_value = classify_info
        except ValueError as error:
            raise ValueError(
                'classify_info should be (areas_unique_key_column, classify_column, classify_value)'
            ) from error

        #: Make sure parcel is associated with an area- areas_unique_key_col is not null
        classify_mask = merged_parcels[areas_unique_key_column].notna()
        merged_parcels.loc[classify_mask, classify_column] = classify_value

    return merged_parcels.copy()


def get_common_areas_intersecting_parcels_by_key(common_areas_df, parcels_df, common_area_key_col):
    """Subset common areas based on a key found in both the parcels and common areas to avoid areas with no parcels

    Some common areas may extend beyond the spatial extent of the parcels. Using the common area identifier spatially copied to the parcels in an earlier step as a key, this gets only the common areas found within the parcels. Because the area geometries are then merged with the other evaluated parcels, this prevents adding blank or superfluous geometries. Basically a right join of common areas and parcels based on the common area key.

    Args:
        common_areas_df (pd.DataFrame): Common areas dataframe; may extend spatially beyond parcels extent
        parcels_df (pd.DataFrame): Dataframe of parcels being evaluated. Must share common_area_key_col with common_areas_df.
        common_area_key_col (str): Column name holding key between parcels and common areas.

    Returns:
        pd.DataFrame: Spatial dataframe of only the common areas found in the parcels.
    """
    parcels_common_area_keys = parcels_df[common_area_key_col]
    common_areas_subset_df = common_areas_df[common_areas_df[common_area_key_col].isin(parcels_common_area_keys)].copy()
    return common_areas_subset_df


def concat_cities_metro_townships(cities_df, townships_df):
    """Concattanate cities and metro townships into a single dataframe with specific fields

    Args:
        cities_df (pd.DataFrame): Cities dataframe with 'name', 'ugrcode', and 'SHAPE' columns
        townships_df (pd.DataFrame): Metro Townships dataframe with 'name', 'ugrcode', and 'SHAPE' columns

    Returns:
        pd.DataFrame: Concattanated spatial dataframe containing only 'name', 'ugrcode', and 'SHAPE' columns
    """

    concat_df = pd.concat([cities_df, townships_df], join='inner')
    return concat_df[['name', 'ugrcode', 'SHAPE']].copy()
