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


def owned_unit_groupings(parcels_df, common_area_key_col, address_points_df) -> pd.DataFrame.spatial:

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

    #: use groupby to summarize the parcel attributes
    #: each series should be indexed by the common_area_key_col
    parcels_grouped_by_oug_id = oug_parcels_df.groupby(common_area_key_col)
    total_mkt_value_sum_series = parcels_grouped_by_oug_id['TOTAL_MKT_VALUE'].sum()
    land_mkt_value_sum_series = parcels_grouped_by_oug_id['LAND_MKT_VALUE'].sum()
    bldg_sqft_sum_series = parcels_grouped_by_oug_id['BLDG_SQFT'].sum()
    floors_cnt_mean_series = parcels_grouped_by_oug_id['FLOORS_CNT'].mean()
    built_yr_series = helpers.get_proper_built_yr_value_series(oug_parcels_df, common_area_key_col, 'BUILT_YR')
    parcel_count_series = parcels_grouped_by_oug_id['SHAPE'].count().rename('PARCEL_COUNT')
    address_count_series = helpers.get_address_point_count_series(
        oug_parcels_df, address_points_df, common_area_key_col
    )

    #: Merge all our new info to the common area polygons, using the common_area_key_col as the df index
    carry_over_fields = ['PARCEL_ID', 'SHAPE', 'CENTROIDS', 'POLYS', common_area_key_col]
    evaluated_oug_parcels_df = pd.concat([
        parcels_df[carry_over_fields].copy().set_index(common_area_key_col),
        total_mkt_value_sum_series,
        land_mkt_value_sum_series,
        bldg_sqft_sum_series,
        floors_cnt_mean_series,
        built_yr_series,
        parcel_count_series,
        address_count_series,
    ])

    #: Set type, subtype, basebldg, building_type_id
    evaluated_oug_parcels_with_types_df = helpers.set_common_area_types(evaluated_oug_parcels_df)

    #: TODO: implement some sort of count tracking. Maybe a separate data frame consisting of just the parcel ids, removing matching ones on each pass?

    return evaluated_oug_parcels_with_types_df


#: TODO: combine these three into one method, passing a list for parcel_type and using .isin(), passing a dict for
#: type/subtype/etc assignments, and a boolean for address counts (need to figure out mf/sf subtypes helper method)
def single_family(parcels_df) -> pd.DataFrame.spatial:
    #: Query out 'single_family' parcels from main parcel feature class
    #: Update type, subtype ('single_family'), basebldg, building_type_id (1)

    single_family_parcels_df = parcels_df[parcels_df['parcel_type'] == 'single_family'].copy()
    single_family_parcels_df['TYPE'] = 'single_family'
    single_family_parcels_df['SUBTYPE'] = 'single_family'
    single_family_parcels_df['basebldg'] = '1'
    single_family_parcels_df['building_type_id'] = '1'

    return single_family_parcels_df


def multi_family_single_parcel(parcels_df, address_pts_df) -> pd.DataFrame.spatial:
    #: Query out various multi-family parcels from main parcel feature class
    #: Update type, subtype
    #:      subtype comes from 'parcel_type' attribute, tri-quad changed to apartment but saved in NOTE column
    #: Spatially join address points to queried parcels, calculate count

    mf_single_parcels_df = parcels_df[parcels_df['parcel_type'].isin([
        'multi_family', 'duplex', 'apartment', 'townhome', 'triplex-quadplex'
    ])].copy()
    mf_single_parcels_df['TYPE'] = 'multi_family'
    mf_single_parcels_df['basebldg'] = '1'
    mf_single_parcels_df['building_type_id'] = '2'

    mf_single_parcels_subtypes_df = helpers.set_multi_family_single_parcel_subtypes(mf_single_parcels_df)
    mf_addr_pt_counts_series = helpers.get_address_point_count_series(
        mf_single_parcels_subtypes_df, address_pts_df, 'PARCEL_ID'
    )

    mf_with_addr_counts_df = mf_single_parcels_subtypes_df.merge(mf_addr_pt_counts_series, how='left', on='PARCEL_ID')

    return mf_with_addr_counts_df


def mobile_home_communities(parcels_df, address_pts_df) -> pd.DataFrame.spatial:
    #: Select parcels that have their center in mobile home boundaries or are classified as mobile_home_park
    #: Set type ='multi_family', subtype = 'mobile_home_park'
    #: Count addresses in area

    mobile_home_communities_parcels_df = parcels_df[parcels_df['parcel_type'] == 'mobile_home_park']

    mobile_home_communities_parcels_df['TYPE'] = 'multi_family'
    mobile_home_communities_parcels_df['SUBTYPE'] = 'mobile_home_park'
    mobile_home_communities_parcels_df['basebldg'] = '1'

    mhc_addr_pt_counts_series = helpers.get_address_point_count_series(
        mobile_home_communities_parcels_df, address_pts_df, 'PARCEL_ID'
    )

    mhc_with_addr_counts_df = mobile_home_communities_parcels_df.merge(
        mhc_addr_pt_counts_series, how='left', on='PARCEL_ID'
    )

    return mhc_with_addr_counts_df
