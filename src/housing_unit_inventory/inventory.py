import os

import arcpy
import pandas as pd
from arcgis.features import GeoAccessor, GeoSeriesAccessor
from arcgis.geometry import Geometry

from housing_unit_inventory import helpers


def evalute_pud_df(parcels_df, common_area_df, address_points_df, index_col='PARCEL_ID'):

    #: Summarize specific fields of parcels that intersect the common area with specific stats for each field
    #:      Save summaries to common area parcels
    #:      Need to convert parcels to centroids to ensure spatial join is accurate
    #: Count number of address points in the common area parcel
    #: BUILT_YR should be most common or latest (if most common is 0)

    # fields = {
    #     'TOTAL_MKT_VALUE': 'Sum',
    #     'LAND_MKT_VALUE': 'Sum',
    #     'BLDG_SQFT': 'Sum',
    #     'FLOORS_CNT': 'Mean',
    #     'BUILT_YR': 'Mode',
    #     'BUILT_YR2': 'Max',
    # }

    #: arcgis.geometry.get_area, .contains, .centroid

    #: Round trip parcels through arcpy to get centroids
    helpers.change_geometry(parcels_df, 'CENTROIDS', 'POLYS')

    pud_parcels_df = common_area_df.spatial.join(parcels_df, 'inner', 'contains')

    total_mkt_value_sum_series = pud_parcels_df.groupby(index_col)['TOTAL_MKT_VALUE'].sum()
    land_mkt_value_sum_series = pud_parcels_df.groupby(index_col)['LAND_MKT_VALUE'].sum()
    bldg_sqft_sum_series = pud_parcels_df.groupby(index_col)['BLDG_SQFT'].sum()
    floors_cnt_mean_series = pud_parcels_df.groupby(index_col)['FLOORS_CNT'].mean()
    built_yr_series = helpers.get_proper_built_yr_value_series(pud_parcels_df, index_col, 'BUILT_YR')

    evaluated_pud_parcels_df = pd.concat([
        common_area_df.set_index(index_col),
        total_mkt_value_sum_series,
        land_mkt_value_sum_series,
        bldg_sqft_sum_series,
        floors_cnt_mean_series,
        built_yr_series,
    ])

    evaluated_pud_parcels_df['TYPE'] = 'single_family'
    evaluated_pud_parcels_df['SUBTYPE'] = 'pud'


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
    address_pts_no_base = pd.DataFrame.spatial.from_featureclass(address_pts)

    #: Prep Main Parcel Layer
    # select parcels within modeling area
    # parcels_in_study_area = _get_parcels_in_modelling_area(parcels, taz_shp, scratch)

    #: Dissolve duplicate parcel ids
    parcels_cleaned_df = helpers.dissolve_duplicate_parcels(parcels_fc)

    #: Add second built year field for handling mode/max built year values
    #: May not need this, may be able to handle 0 in BUILT_YR during the analysis phase rather than doing it later
    parcels_cleaned_df['BUILT_YR2'] = parcels_cleaned_df['BUILT_YR']

    # Load Extended Descriptions - be sure to format ACCOUNTNO column as text in excel first
    # parcels_for_modeling_layer = _join_extended_parcel_info(davis_extended, parcels_cleaned_df, scratch)

    extra_data_df = helpers.read_extra_info_into_dataframe(
        extended_info_csv, 'ACCOUNTNO', str, 9, ['ACCOUNTNO', 'des_all', 'class']
    )
    parcels_merged_df = parcels_cleaned_df.merge(extra_data_df, left_on='PARCEL_ID', right_on='ACCOUNTNO', how='left')

    parcels_with_centroids_df = helpers.add_centroids_to_parcel_df(parcels_merged_df, 'PARCEL_ID')

    #: Fields can just be added as dataframe columns when needed
    # fields = {
    #     'TYPE': 'TEXT',
    #     'SUBTYPE': 'TEXT',
    #     'NOTE': 'TEXT',
    #     'BUILT_YR2': 'SHORT',
    # }
    # parcels_for_modeling_layer = _add_fields(parcels_for_modeling_layer, fields)

    # get a count of all parcels
    count_all = parcels_with_centroids_df.shape[0]
    print(f'# initial parcels in modeling area:\n {count_all}')

    common_areas_df = pd.DataFrame.spatial.from_featureclass(common_areas_fc)
    pud_common_areas_df = common_areas_df[common_areas_df['SUBTYPE_WFRC'] == 'pud']
    pud_common_areas_df['IS_OUG'] = 1
    multi_family_common_areas_df = common_areas_df[common_areas_df['TYPE_WFRC'] == 'multi_family']
    multi_family_common_areas_df['IS_OUG'] = 1
