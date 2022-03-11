import warnings
from datetime import datetime

import arcpy
import numpy as np
import pandas as pd


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

    csv_df.dropna(subset=['ACCOUNTNO'], inplace=True)

    try:
        parcels_merged_df = parcels_df.merge(
            csv_df[csv_fields], left_on='PARCEL_ID', right_on=csv_join_field, how='left', validate='m:1'
        )
    except pd.errors.MergeError as error:
        raise ValueError(f'Values in csv join field {csv_join_field} are not unique.') from error

    return parcels_merged_df


def add_centroids_to_parcel_df(parcels_df, join_field):
    memory_parcels = 'memory/parcels'
    memory_centroids = 'memory/centroids'

    for featureclass in [memory_centroids, memory_parcels]:
        if arcpy.Exists(featureclass):
            arcpy.management.Delete(featureclass)

    parcels_df.spatial.to_featureclass(memory_parcels)
    arcpy.management.FeatureToPoint(memory_parcels, memory_centroids, 'INSIDE')
    centroids_df = (
        pd.DataFrame.spatial.from_featureclass(memory_centroids)[[join_field.lower(), 'SHAPE']].rename(
            columns={
                'SHAPE': 'CENTROIDS',
                join_field.lower(): join_field
            }
        )  #: feature class lowercases the columns
        .assign(**{join_field: lambda df: df[join_field].astype(str)})  #: ensure it's a str for join
    )

    joined_df = parcels_df.merge(centroids_df, on=join_field, how='left')

    blank_centroids = joined_df['CENTROIDS'].isna().sum()
    if blank_centroids:
        print(f'{blank_centroids} blank centroids!')

    return joined_df


def load_and_clean_parcels(parcels_fc):

    parcels_dissolved_fc = 'memory/dissolved'
    if arcpy.Exists(parcels_dissolved_fc):
        arcpy.management.Delete(parcels_dissolved_fc)

    arcpy.management.Dissolve(
        str(parcels_fc), parcels_dissolved_fc, 'PARCEL_ID', [
            ['PARCEL_ID', 'COUNT'],
            ['TAXEXEMPT_TYPE', 'FIRST'],
            ['TOTAL_MKT_VALUE', 'SUM'],
            ['LAND_MKT_VALUE', 'SUM'],
            ['PARCEL_ACRES', 'SUM'],
            ['PROP_CLASS', 'FIRST'],
            ['PRIMARY_RES', 'FIRST'],
            ['HOUSE_CNT', 'MAX'],
            ['BLDG_SQFT', 'SUM'],
            ['FLOORS_CNT', 'MAX'],
            ['BUILT_YR', 'FIRST'],
            ['EFFBUILT_YR', 'FIRST'],
        ], 'MULTI_PART', 'DISSOLVE_LINES'
    )

    parcels_dissolved_df = pd.DataFrame.spatial.from_featureclass(parcels_dissolved_fc)

    #: Remove stats from field names
    cleaned_fields = clean_dissolve_field_names(list(parcels_dissolved_df.columns), ['FIRST', 'SUM', 'MAX'])
    parcels_dissolved_df.rename(columns=cleaned_fields, inplace=True)

    #: Remove parcels without parcel ids and empty geometries
    parcels_dissolved_df.dropna(subset=['PARCEL_ID', 'SHAPE'], inplace=True)

    return parcels_dissolved_df


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

    # get address points without base address point
    address_pts_no_base_df = (
        pd.DataFrame.spatial.from_featureclass(address_pts_fc) \
        .query(f'{type_column_name} != @base_address_value')
        )
    return address_pts_no_base_df


def set_common_area_types(evaluated_df):

    evaluated_df['TYPE'] = ''
    evaluated_df['SUBTYPE'] = ''
    evaluated_df['basebldg'] = ''
    evaluated_df['building_type_id'] = ''

    evaluated_df.loc[evaluated_df['SUBTYPE_WFRC'] == 'pud', 'TYPE'] = 'single_family'
    evaluated_df.loc[evaluated_df['SUBTYPE_WFRC'] == 'pud', 'SUBTYPE'] = 'pud'
    evaluated_df.loc[evaluated_df['SUBTYPE_WFRC'] == 'pud', 'basebldg'] = '1'
    evaluated_df.loc[evaluated_df['SUBTYPE_WFRC'] == 'pud', 'building_type_id'] = '1'

    evaluated_df.loc[evaluated_df['TYPE_WFRC'] == 'multi_family', 'TYPE'] = 'multi_family'
    evaluated_df.loc[evaluated_df['TYPE_WFRC'] == 'multi_family', 'basebldg'] = '1'
    evaluated_df.loc[evaluated_df['TYPE_WFRC'] == 'multi_family', 'building_type_id'] = '2'

    return evaluated_df


def subset_owned_unit_groupings_from_common_areas(
    common_areas_fc, common_area_key_column_name, unique_key_column='OBJECTID'
):
    """Get PUDs and multi-family parcels from common_areas_fc as a dataframe

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
    common_areas_subset_df['IS_OUG'] = 1

    return common_areas_subset_df


def set_multi_family_single_parcel_subtypes(evaluated_df):
    #: SUBTYPE = class unless class == 'triplex-quadplex', in which case it becomes 'apartment' and NOTE becomes tri-quad

    evaluated_df['SUBTYPE'] = np.where(
        evaluated_df['parcel_type'] != 'triplex-quadplex', evaluated_df['parcel_type'], 'apartment'
    )
    evaluated_df['NOTE'] = np.where(evaluated_df['parcel_type'] != 'triplex-quadplex', '', evaluated_df['parcel_type'])

    return evaluated_df


def get_address_point_count_series(parcels_df, address_points_df, key_col):
    """Add number of intersecting address points as the UNIT_COUNT

    Args:
        parcels_df (pd.DataFrame.spatial): Parcels dataset
        address_points_df (pd.DataFrame.spatial): Address point dataset with base addresses filtered out
        key_col (str): A column in parcels_df that identifies the joined rows that belong to a single source parcel/geometry

    Returns:
        pd.Series: The count of addresses, named 'UNIT_COUNT' and indexed by key_col
    """

    address_count_series = (
        parcels_df.spatial.join(address_points_df, 'left', 'contains') \
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

    concated_dataframes = pd.concat(dataframes).set_index(new_index, verify_integrity=True)

    return concated_dataframes


def classify_from_area(parcels_with_centroids_df, area_df, classify_info=()):
    """Spatial join of parcels whose centers are within areas, with optional custom classification

    Performs a left spatial join of parcels to areas, attempting to ensure all parcels are returned whether they are
    inside the areas or not.

    Raises a UserWarning if the number of rows after the spatial join of parcel centroids within the areas is
    different than the original number of parcel rows, or if there are duplicate parcel ids in the joined data (could
    indicate overlapping area geometries.)

    Args:
        parcels_with_centroids_df (pd.DataFrame.spatial): The parcels dataset with centroid shapes in the 'CENTROIDS'
        column.
        area_df (pd.DataFrame.spatial): Areas to use for joining and classification. Should contain any fields to be
        joined as well as (optionally) a unique key column for classification.
        classify_info (tuple, optional): Information for custom classification: (areas_unique_key_column,
        classify_column, classify_value). Defaults to ().

    Raises:
        ValueError: If three values are not passed in classify_info

    Returns:
        pd.DataFrame.spatial: Parcels with area info joined spatially and optional classification added.
    """

    change_geometry(parcels_with_centroids_df, 'CENTROIDS', 'POLYS')
    joined_centroids_df = parcels_with_centroids_df.spatial.join(area_df, 'left', 'within')

    if joined_centroids_df.shape[0] != parcels_with_centroids_df.shape[0]:
        warnings.warn(
            f'Different number of features in joined dataframe ({joined_centroids_df.shape[0]}) than in original '
            f'parcels ({parcels_with_centroids_df.shape[0]})'
        )

    dup_parcel_ids = joined_centroids_df[joined_centroids_df.duplicated(subset=['PARCEL_ID'], keep=False)]
    if dup_parcel_ids.shape[0]:
        warnings.warn(
            f'{dup_parcel_ids.shape[0]} duplicate parcel IDs found in join; check areas features for overlaps'
        )

    if classify_info:
        #: Make sure we've got all the necessary classification info
        try:
            areas_unique_key_column, classify_column, classify_value = classify_info
        except ValueError as error:
            raise ValueError(
                'classify_info should be (areas_unique_key_column, classify_column, classify_value)'
            ) from error

        classify_mask = joined_centroids_df[areas_unique_key_column].notna()
        joined_centroids_df.loc[classify_mask, classify_column] = classify_value

    change_geometry(joined_centroids_df, 'POLYS', 'CENTROIDS')

    #: Remove 'index_left' left over from spatial join
    joined_centroids_df.drop(columns=['index_right'], inplace=True)

    return joined_centroids_df.copy()


def update_unit_count(parcels_df):
    """Update unit counts in-place for single family, duplex, and tri/quad

    Args:
        parcels_df (pd.DataFrame): The evaluated parcel dataset with UNIT_COUNT, HOUSE_CNT, SUBTYPE, and NOTE columns
    """

    # fix single family (non-pud)
    parcels_df.loc[(parcels_df['UNIT_COUNT'] == 0) & (parcels_df['SUBTYPE'] == 'single_family'), 'UNIT_COUNT'] = 1

    # fix duplex
    parcels_df.loc[(parcels_df['SUBTYPE'] == 'duplex'), 'UNIT_COUNT'] = 2

    # fix triplex-quadplex
    parcels_df.loc[(parcels_df['UNIT_COUNT'] < parcels_df['HOUSE_CNT']) & (parcels_df['NOTE'] == 'triplex-quadplex'),
                   'UNIT_COUNT'] = parcels_df['HOUSE_CNT']


def remove_zero_unit_house_counts(parcels_df):
    """Remove any rows in-place that have a 0 or null in either UNIT_COUNT or HOUSE_CNT

    Args:
        parcels_df (pd.DataFrame): Parcels dataset with populated UNIT_COUNT and HOUSE_CNT columns
    """

    rows_with_zeros = parcels_df[(parcels_df['UNIT_COUNT'] == 0) | (parcels_df['HOUSE_CNT'] == 0)]
    parcels_df.drop(rows_with_zeros.index, inplace=True)
    parcels_df.dropna(subset=['UNIT_COUNT', 'HOUSE_CNT'], inplace=True)


def calculate_built_decade(parcels_df):
    """Calculate BUILT_DECADE from BUILT_YR in-place

    Raises a UserWarning with the number of rows whose BUILT_YR is before 1846 or after the current year + 2 (yes,
    there were structures prior to Fort Buenaventura, but I highly doubt any are still in use as housing).

    Args:
        parcels_df (pd.DataFrame): Parcels dataset with BUILT_YR column
    """

    this_year = datetime.now().year
    invalid_built_year_rows = parcels_df[(parcels_df['BUILT_YR'] < 1846) | (parcels_df['BUILT_YR'] > this_year + 2)]
    if invalid_built_year_rows.shape[0]:
        warnings.warn(
            f'{invalid_built_year_rows.shape[0]} parcels have an invald built year (before 1847 or after current '
            'year plus two)'
        )

    #: Decade is floor division by 10, then multiply by 10
    parcels_df['BUILT_DECADE'] = parcels_df['BUILT_YR'] // 10 * 10
