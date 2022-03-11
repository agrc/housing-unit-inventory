import logging

import pandas as pd
from arcgis.features import GeoAccessor, GeoSeriesAccessor
from arcgis.geometry import Geometry

from . import helpers

#: TYPE (and SUBTYPE)
#:  single-family
#:      single-family
#:      pud
#:  multi-family
#:      duplex
#:      townhome
#:      apartment
#:      multi-family
#:      mobile_home_park


def owned_unit_groupings(parcels_df, common_area_key_col, address_points_df, common_area_df) -> pd.DataFrame.spatial:

    #: common_area_key_col: a unique key (probably just a copied ObjectID?) for all the common areas

    #: Summarize specific fields of parcels that intersect the common area with specific stats for each field
    #:      Save summaries to common area parcels
    #:      Need to convert parcels to centroids to ensure spatial join is accurate
    #:      Count number of parcels in the common area
    #: Count number of address points in the common area parcel
    #: BUILT_YR should be most common or latest (if most common is 0)

    # fields = {
    #     'TOTAL_MKT_VALUE': 'Sum',
    #     'LAND_MKT_VALUE': 'Sum',
    #     'BLDG_SQFT': 'Sum',
    #     'FLOORS_CNT': 'Mean',
    #     'BUILT_YR': 'Mode', (or max if mode=0/multiple)
    # }

    #: arcgis.geometry.get_area, .contains, .centroid

    oug_parcels_df = parcels_df[parcels_df['parcel_type'] == 'owned_unit_grouping'].copy()

    logging.debug(f'{oug_parcels_df.shape[0]} parcels being evaluated as owned unit groupings...')

    #: use groupby to summarize the parcel attributes per common area
    #: each series should be indexed by and refere back to the common_area_key_col, not the parcels
    parcels_grouped_by_oug_id = oug_parcels_df.groupby(common_area_key_col)
    total_mkt_value_sum_series = parcels_grouped_by_oug_id['TOTAL_MKT_VALUE'].sum()
    land_mkt_value_sum_series = parcels_grouped_by_oug_id['LAND_MKT_VALUE'].sum()
    bldg_sqft_sum_series = parcels_grouped_by_oug_id['BLDG_SQFT'].sum()
    floors_cnt_mean_series = parcels_grouped_by_oug_id['FLOORS_CNT'].mean()
    built_yr_series = helpers.get_proper_built_yr_value_series(oug_parcels_df, common_area_key_col, 'BUILT_YR')
    parcel_count_series = parcels_grouped_by_oug_id['SHAPE'].count().rename('PARCEL_COUNT')
    address_count_series = helpers.get_address_point_count_series(
        common_area_df, address_points_df, common_area_key_col
    )

    #: Merge all our new info to the common area polygons, using the common_area_key_col as the df index
    carry_over_fields = ['SHAPE', common_area_key_col, 'SUBTYPE_WFRC', 'TYPE_WFRC']
    evaluated_oug_parcels_df = pd.concat(
        axis=1,
        objs=[
            common_area_df[carry_over_fields].copy().set_index(common_area_key_col),
            total_mkt_value_sum_series,
            land_mkt_value_sum_series,
            bldg_sqft_sum_series,
            floors_cnt_mean_series,
            built_yr_series,
            parcel_count_series,
            address_count_series,
        ]
    )

    #: Set type, subtype, basebldg, building_type_id
    evaluated_oug_parcels_with_types_df = helpers.set_common_area_types(evaluated_oug_parcels_df)

    #: Add a generated PARCEL_ID based on the common_area_key for future aligning with other parcels
    evaluated_oug_parcels_with_types_df['PARCEL_ID'] = 'oug_' + evaluated_oug_parcels_with_types_df.index.astype(str)

    #: TODO: implement some sort of count tracking. Maybe a separate data frame consisting of just the parcel ids, removing matching ones on each pass?

    return evaluated_oug_parcels_with_types_df


def by_parcel_types(parcels_df, parcel_types, attribute_dict, address_points_df=None, subtypes_method=None):
    """Run the evaluations subsetting by various parcel_types.

    Add TYPE, SUBTYPE, basebldg, building_type_id, based on values set in attribute_dict. Add UNIT_COUNT based on
    address points if passed in via address_points_df. Set SUBTYPE and add NOTE if
    helpers.set_multi_family_single_parcel_subtypes is passed via subtypes_method.

    Args:
        parcels_df (pd.DataFrame): Parcels dataset with a unique PARCEL_ID column
        parcel_types (List<str>): parcel_types to include in this particular evaluation
        attribute_dict (dict): Attribute names and values to set in the subsetted parcels
        address_points_df (pd.DataFrame.spatial, optional): If provided, calculates the number of address points in
        each parcel. Defaults to None.
        subtypes_method (method, optional): If provided, call this method with the parcels subset as a parameter to set
        the subtype (used to reassign tri-quad to apartment). Defaults to None.

    Returns:
        pd.DataFrame: The subset of parcels with the appropriate fields added.
    """

    working_parcels_df = parcels_df[parcels_df['parcel_type'].isin(parcel_types)].copy()
    for attribute, value in attribute_dict.items():
        working_parcels_df[attribute] = value

    if subtypes_method:
        working_parcels_df = subtypes_method(working_parcels_df)

    if address_points_df:
        address_points_series = helpers.get_address_point_count_series(
            working_parcels_df, address_points_df, 'PARCEL_ID'
        )
        parcels_with_addr_pts_df = working_parcels_df.merge(address_points_series, how='left', on='PARCEL_ID')
        return parcels_with_addr_pts_df

    return working_parcels_df
