import os

import arcpy
import pandas as pd
from arcgis.features import GeoAccessor, GeoSeriesAccessor
from arcgis.geometry import Geometry

from housing_unit_inventory import helpers

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


def evalute_pud_df(parcels_df, common_area_df, common_area_key_col, address_points_df) -> pd.DataFrame.spatial:

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

    #: Convert parcels to centroids and join them to common area polygons
    helpers.change_geometry(parcels_df, 'CENTROIDS', 'POLYS')
    pud_parcels_df = common_area_df.spatial.join(
        parcels_df, 'inner', 'contains'
    )  #: Does inner join only get the parcels that are

    #: use groupby to summarize the parcel attributes
    #: each series should be indexed by the common_area_key_col
    parcels_grouped_by_pud_id = pud_parcels_df.groupby(common_area_key_col)
    total_mkt_value_sum_series = parcels_grouped_by_pud_id['TOTAL_MKT_VALUE'].sum()
    land_mkt_value_sum_series = parcels_grouped_by_pud_id['LAND_MKT_VALUE'].sum()
    bldg_sqft_sum_series = parcels_grouped_by_pud_id['BLDG_SQFT'].sum()
    floors_cnt_mean_series = parcels_grouped_by_pud_id['FLOORS_CNT'].mean()
    built_yr_series = helpers.get_proper_built_yr_value_series(pud_parcels_df, common_area_key_col, 'BUILT_YR')
    parcel_count_series = parcels_grouped_by_pud_id['SHAPE'].count().rename('parcel_count')
    address_count_series = (
        pud_parcels_df.spatial.join(address_points_df, 'left', 'contains') \
        .groupby(common_area_key_col)['SHAPE'].count() \
        .rename('ap_count')
    )

    #: Merge all our new info to the common area polygons, using the common_area_key_col as the df index
    evaluated_pud_parcels_df = pd.concat([
        common_area_df.set_index(common_area_key_col),
        total_mkt_value_sum_series,
        land_mkt_value_sum_series,
        bldg_sqft_sum_series,
        floors_cnt_mean_series,
        built_yr_series,
        parcel_count_series,
        address_count_series,
    ])

    #: Set type, subtype, basebldg, building_type_id
    evaluated_common_area_parcels_with_types_df = helpers.set_common_area_types(evaluated_pud_parcels_df)

    #: TODO: implement some sort of count tracking. Maybe a separate data frame consisting of just the parcel ids, removing matching ones on each pass?

    return evaluated_common_area_parcels_with_types_df


def evaluate_single_family_df(parcels_df) -> pd.DataFrame.spatial:
    #: Query out 'single_family' parcels from main parcel feature class
    #: Update type, subtype ('single_family'), basebldg, building_type_id (1)

    single_family_parcels_df = parcels_df[parcels_df['parcel_type'] == 'single_family'].copy()
    single_family_parcels_df['TYPE'] = 'single_family'
    single_family_parcels_df['SUBTYPE'] = 'single_family'
    single_family_parcels_df['basebldg'] = '1'
    single_family_parcels_df['building_type_id'] = '1'

    return single_family_parcels_df


def evaluate_multi_family_single_parcel_df(parcels_df, address_pts_df) -> pd.DataFrame.spatial:
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


def davis_by_dataframe():
    arcpy.env.overwriteOutput = True

    #: Inputs
    taz_shp = '.\\Inputs\\TAZ.shp'
    parcels_fc = '.\\Inputs\\Davis_County_LIR_Parcels.gdb\\Parcels_Davis_LIR_UTM12'
    address_pts = '.\\Inputs\\AddressPoints_Davis.gdb\\address_points_davis'
    common_areas_fc = r'.\Inputs\Common_Areas.gdb\Common_Areas_Reviewed'
    extended_info_csv = r'.\Inputs\davis_extended_simplified.csv'
    mobile_home_communities = '.\\Inputs\\Mobile_Home_Parks.shp'

    # create output gdb
    outputs = '.\\Outputs'
    gdb = os.path.join(outputs, 'classes_HUI.gdb')
    if not arcpy.Exists(gdb):
        arcpy.CreateFileGDB_management(outputs, 'classes_HUI.gdb')

    scratch = os.path.join(outputs, 'scratch_HUI.gdb')
    if not arcpy.Exists(scratch):
        arcpy.CreateFileGDB_management(outputs, 'scratch_HUI.gdb')

    #: Address points (used later)
    # address_pts_no_base = helpers.get_non_base_addr_points(address_pts, scratch)
    address_pts_no_base_df = pd.DataFrame.spatial.from_featureclass(address_pts)

    #: Prep Main Parcel Layer
    # select parcels within modeling area
    # parcels_in_study_area = _get_parcels_in_modelling_area(parcels, taz_shp, scratch)

    #: Dissolve duplicate parcel ids
    parcels_cleaned_df = helpers.dissolve_duplicate_parcels(parcels_fc)

    # Load Extended Descriptions - be sure to format ACCOUNTNO column as text in excel first
    # parcels_for_modeling_layer = _join_extended_parcel_info(davis_extended, parcels_cleaned_df, scratch)

    extra_data_df = helpers.read_extra_info_into_dataframe(
        extended_info_csv, 'ACCOUNTNO', str, 9, ['ACCOUNTNO', 'des_all', 'class']
    )
    parcels_merged_df = parcels_cleaned_df.merge(extra_data_df, left_on='PARCEL_ID', right_on='ACCOUNTNO', how='left')

    parcels_with_centroids_df = helpers.add_centroids_to_parcel_df(parcels_merged_df, 'PARCEL_ID')

    davis_field_mapping = {
        'class': 'parcel_type',
    }
    standardized_parcels_df = helpers.standardize_fields(parcels_with_centroids_df, davis_field_mapping)

    #: Fields can just be added as dataframe columns when needed
    # fields = {
    #     'TYPE': 'TEXT',
    #     'SUBTYPE': 'TEXT',
    #     'NOTE': 'TEXT',
    #     'BUILT_YR2': 'SHORT',
    # }
    # parcels_for_modeling_layer = _add_fields(parcels_for_modeling_layer, fields)

    # get a count of all parcels
    count_all = standardized_parcels_df.shape[0]
    print(f'# initial parcels in modeling area:\n {count_all}')

    #: These get a little dicey- puds/multi family are dq'd out, and their parcels are removed from the analysis.
    #: I really want to change this so that each category has an appropriate dq.
    common_area_key = 'common_area_key'
    common_areas_df = pd.DataFrame.spatial.from_featureclass(common_areas_fc)
    common_areas_df[common_area_key] = common_areas_df['OBJECTID']

    common_areas_subset_df = common_areas_df[(common_areas_df['SUBTYPE_WFRC'] == 'pud') |
                                             (common_areas_df['TYPE_WFRC'] == 'multi_family')]
    common_areas_subset_df['IS_OUG'] = 1

    #: TODO: we may need to remove the parcels evaluated for common areas because everything else is based on the 'class' attribute
    pud_features_df = evalute_pud_df(
        standardized_parcels_df, common_areas_subset_df, common_area_key, address_pts_no_base_df
    )

    single_family_features_df = evaluate_single_family_df(standardized_parcels_df)

    multi_family_single_parcel_features_df = evaluate_multi_family_single_parcel_df(
        standardized_parcels_df, address_pts_no_base_df
    )
