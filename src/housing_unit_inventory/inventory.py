import logging
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


def evalute_owned_unit_groupings_df(
    parcels_df, common_area_df, common_area_key_col, address_points_df
) -> pd.DataFrame.spatial:

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

    # #: Convert parcels to centroids and join them to common area polygons
    # helpers.change_geometry(parcels_df, 'CENTROIDS', 'POLYS')
    # pud_parcels_df = common_area_df.spatial.join(
    #     parcels_df, 'inner', 'contains'
    # )  #: Does inner join only get the parcels that are

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
    #: TODO: Do we need to change common_area_df.set_index to oug_parcels_df.set_index?
    #: I don't think so... we create new "parcels" based off the oug geometries and get their column values from the
    #: aggregation methods above. We may need to add a few other columns, though, to amke sure they have any other
    #: needed info.
    evaluated_oug_parcels_df = pd.concat([
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
    evaluated_oug_parcels_with_types_df = helpers.set_common_area_types(evaluated_oug_parcels_df)

    #: TODO: implement some sort of count tracking. Maybe a separate data frame consisting of just the parcel ids, removing matching ones on each pass?

    return evaluated_oug_parcels_with_types_df


#: TODO: combine these three into one method, passing a list for parcel_type and using .isin(), passing a dict for
#: type/subtype/etc assignments, and a boolean for address counts (need to figure out mf/sf subtypes helper method)
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


def evaluate_mobile_home_communities_df(parcels_df, address_pts_df) -> pd.DataFrame.spatial:
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


def davis_by_dataframe():
    arcpy.env.overwriteOutput = True

    #: Inputs
    # taz_shp = '.\\Inputs\\TAZ.shp'
    parcels_fc = '.\\Inputs\\Davis_County_LIR_Parcels.gdb\\Parcels_Davis_LIR_UTM12'
    address_pts = '.\\Inputs\\AddressPoints_Davis.gdb\\address_points_davis'
    common_areas_fc = r'.\Inputs\Common_Areas.gdb\Common_Areas_Reviewed'
    extended_info_csv = r'.\Inputs\davis_extended_simplified.csv'
    mobile_home_communities = '.\\Inputs\\Mobile_Home_Parks.shp'
    cities = r'.\Inputs\Cities.shp'
    subcounties = r'.\Inputs\SubCountyArea_2019.shp'

    #: Output
    output_fc = r'c:\gis\projects\housinginventory\housinginventory.gdb\davis2020_1'
    output_csv = r'c:\gis\projects\housinginventory\davis2020_1.csv'

    #: Address points (used later)
    address_pts_no_base_df = helpers.get_non_base_addr_points(address_pts)

    #: Prep Main Parcel Layer
    # select parcels within modeling area
    # parcels_in_study_area = _get_parcels_in_modelling_area(parcels, taz_shp, scratch)

    #: Dissolve duplicate parcel ids
    logging.debug('Dissolving parcels...')
    parcels_cleaned_df = helpers.dissolve_duplicate_parcels(parcels_fc)

    #: Load Extended Descriptions - be sure to format ACCOUNTNO column as text in excel first
    logging.debug('Merging csv data...')
    extra_data_df = helpers.read_extra_info_into_dataframe(
        extended_info_csv, 'ACCOUNTNO', str, 9, ['ACCOUNTNO', 'des_all', 'class']
    )
    parcels_merged_df = parcels_cleaned_df.merge(extra_data_df, left_on='PARCEL_ID', right_on='ACCOUNTNO', how='left')

    logging.debug('Creating centroid shapes...')
    parcels_with_centroids_df = helpers.add_centroids_to_parcel_df(parcels_merged_df, 'PARCEL_ID')

    davis_field_mapping = {
        'class': 'parcel_type',
    }
    standardized_parcels_df = helpers.standardize_fields(parcels_with_centroids_df, davis_field_mapping)

    #: Get a count of all parcels
    count_all = standardized_parcels_df.shape[0]
    print(f'Initial parcels in modeling area:\t {count_all}')

    logging.debug('Classifying OUGs and MHCs...')
    #: Classify parcels within common areas
    common_area_key = 'common_area_key'
    common_areas_df = pd.DataFrame.spatial.from_featureclass(common_areas_fc)
    common_areas_df[common_area_key] = common_areas_df['OBJECTID']
    common_areas_subset_df = common_areas_df[(common_areas_df['SUBTYPE_WFRC'] == 'pud') |
                                             (common_areas_df['TYPE_WFRC'] == 'multi_family')]
    common_areas_subset_df['IS_OUG'] = 1

    common_area_classify_info = (common_area_key, 'parcel_type', 'owned_unit_grouping')
    parcels_with_oug_df = helpers.classify_from_area(
        standardized_parcels_df, common_areas_subset_df, common_area_classify_info
    )

    #: Classify parcels within mobile home communities
    mobile_home_key = 'mobile_home_key'
    mobile_home_communities_df = pd.DataFrame.spatial.from_featureclass(mobile_home_communities)
    mobile_home_communities_df[mobile_home_key] = mobile_home_communities_df['OBJECTID']

    mobile_home_classify_info = (common_area_key, 'parcel_type', 'mobile_home_park')
    classified_parcels_df = helpers.classify_from_area(
        parcels_with_oug_df, mobile_home_communities_df, mobile_home_classify_info
    )

    #: Run the evaluations
    logging.info('Evaluating owned unit groupings...')
    oug_features_df = evalute_owned_unit_groupings_df(
        classified_parcels_df, common_areas_subset_df, common_area_key, address_pts_no_base_df
    )

    logging.info('Evaluating single family parcels...')
    single_family_features_df = evaluate_single_family_df(classified_parcels_df)

    logging.info('Evaluating multi-family, single-parcel parcels...')
    multi_family_single_parcel_features_df = evaluate_multi_family_single_parcel_df(
        classified_parcels_df, address_pts_no_base_df
    )

    logging.info('Evaluating mobile home communities...')
    mobile_home_communities_features_df = evaluate_mobile_home_communities_df(
        classified_parcels_df, address_pts_no_base_df
    )

    #: Merge the evaluated parcels into one dataframe
    logging.debug('Merging dataframes...')
    evaluated_parcels_df = helpers.concat_evaluated_dataframes([
        oug_features_df,
        single_family_features_df,
        multi_family_single_parcel_features_df,
        mobile_home_communities_features_df,
    ])

    #: Add city and sub-county info
    logging.debug('Adding city and subcounty info...')
    cities_df = pd.DataFrame.spatial.from_featureclass(cities)
    parcels_with_cities_df = helpers.classify_from_area(evaluated_parcels_df, cities_df)

    subcounties_df = pd.DataFrame.spatial.from_featureclass(subcounties)
    final_parcels_df = helpers.classify_from_area(parcels_with_cities_df, subcounties_df)

    final_parcels_df['COUNTY'] = 'DAVIS'

    #: Rename fields from city/subcounties
    final_parcels_df.rename(columns={
        'NAME': 'CITY',
        'NewSA': 'SUBREGION',
    }, inplace=True)

    #: Clean up some nulls
    logging.debug('Cleaning up final data')
    final_parcels_df['NOTE'].fillna(final_parcels_df['des_all'], in_place=True)
    final_parcels_df['HOUSE_CNT'] = final_parcels_df['HOUSE_CNT'].fillna(0).astype(int)
    final_parcels_df['UNIT_COUNT'] = final_parcels_df['UNIT_COUNT'].fillna(0).astype(int)

    helpers.update_unit_count(final_parcels_df)

    #: Decade is floor division by 10, then multiply by 10
    final_parcels_df['BUILT_DECADE'] = final_parcels_df['BUILT_YR'] // 10 * 10

    # remove data points with zero units
    helpers.remove_zero_unit_house_counts(final_parcels_df)

    final_fields = [
        'OBJECTID', 'PARCEL_ID', 'TYPE', 'SUBTYPE', 'NOTE', 'IS_OUG', 'CITY', 'SUBREGION', 'COUNTY', 'UNIT_COUNT',
        'PARCEL_COUNT', 'FLOORS_CNT', 'PARCEL_ACRES', 'BLDG_SQFT', 'TOTAL_MKT_VALUE', 'BUILT_YR', 'BUILT_DECADE',
        'SHAPE'
    ]

    logging.info('Writing final data out to disk...')
    output_df = final_parcels_df.reindex(columns=final_fields)
    output_df.spatial.to_featureclass(output_fc)
    output_df.drop(columns=['SHAPE']).to_csv(output_csv)
