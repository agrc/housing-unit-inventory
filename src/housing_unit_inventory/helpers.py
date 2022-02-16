import arcpy
import pandas as pd


def get_proper_built_yr_value_series(parcels_df, index_col, built_yr_col):
    """Return either the most common yearbuilt or the max if the common is 0

    Args:
        parcels_df (pd.DataFrame.spatial): The parcels data
        index_col (str): The primary key of the parcel table (usually a parcel number/id)
        built_yr_col (str): The column holding the built year as an integar/float

    Returns:
        pd.Series: A series of the built year, indexed by the unique values in index_col
    """

    parcels_grouped = parcels_df.groupby(index_col)

    #: Set mode to 0 to start with
    built_yr_mode_series = pd.Series(data=0, index=parcels_grouped.groups.keys(), name=built_yr_col)
    built_yr_mode_series.index.name = index_col
    #: If we can get a single mode value, use that instead
    try:
        built_yr_mode_series = parcels_grouped[built_yr_col].agg(pd.Series.mode)
    #: If there are multiple modes, .mode returns them all and .agg complains there isn't a single value
    except ValueError as error:
        if str(error) == 'Must produce aggregated value':
            pass

    built_yr_max_series = parcels_grouped[built_yr_col].max()
    built_yr_df = pd.DataFrame({'mode': built_yr_mode_series, 'max': built_yr_max_series})
    built_yr_df[built_yr_col] = built_yr_df['mode']
    built_yr_df.loc[built_yr_df[built_yr_col] == 0, built_yr_col] = built_yr_df['max']

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


def read_extra_info_into_dataframe(info_csv, csv_join_field, csv_join_field_type, pad_length, csv_fields):
    csv_df = (
        pd.read_csv(info_csv, dtype={csv_join_field: csv_join_field_type}) \
            .assign(**{csv_join_field: lambda df: df[csv_join_field.zfill(pad_length)]})  #: Pad join field
    )

    return csv_df[csv_fields].copy()


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

    joined_df = parcels_df.join(centroids_df, on=join_field, how='left')

    blank_centroids = joined_df['CENTROIDS'].isna().sum()
    if blank_centroids:
        print(f'{blank_centroids} blank centroids!')

    return joined_df


def dissolve_duplicate_parcels(parcels_for_modeling_layer):
    #: TODO: rename '_clean_parcels' because that's what it does
    # dissolve on parcel id,summarizing attributes in various ways
    parcels_dissolved_fc = 'memory/dissolved'
    if arcpy.Exists(parcels_dissolved_fc):
        arcpy.management.Delete(parcels_dissolved_fc)
    parcels_dissolved = arcpy.management.Dissolve(
        parcels_for_modeling_layer, parcels_dissolved_fc, 'PARCEL_ID', [
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

    # rename columns
    #: moves OBJECTID, COUNT_PARCEL_ID
    parcels_dissolved_df = pd.DataFrame.spatial.from_featureclass(parcels_dissolved)
    parcels_dissolved_df.columns = [
        'OBJECTID',
        'PARCEL_ID',
        'COUNT_PARCEL_ID',
        'TAXEXEMPT_TYPE',
        'TOTAL_MKT_VALUE',
        'LAND_MKT_VALUE',
        'PARCEL_ACRES',
        'PROP_CLASS',
        'PRIMARY_RES',
        'HOUSE_CNT',
        'BLDG_SQFT',
        'FLOORS_CNT',
        'BUILT_YR',
        'EFFBUILT_YR',
        'SHAPE',
    ]

    #: Remove parcels without parcel ids or empty geometries
    parcels_dissolved_df.dropna(subset=['PARCEL_ID', 'SHAPE'], inplace=True)

    return parcels_dissolved_df


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
