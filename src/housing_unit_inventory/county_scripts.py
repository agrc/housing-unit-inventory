import logging

import arcpy
import pandas as pd
from arcgis.features import GeoAccessor, GeoSeriesAccessor

from . import evaluations, helpers


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

    #: Dissolve duplicate parcel ids
    logging.debug('Dissolving parcels...')
    parcels_cleaned_df = helpers.dissolve_duplicate_parcels(parcels_fc)

    #: Load Extended Descriptions - be sure to format ACCOUNTNO column as text in excel first
    logging.debug('Merging csv data...')
    csv_fields = ['ACCOUNTNO', 'des_all', 'class']
    parcels_merged_df = helpers.add_extra_info_from_csv(extended_info_csv, 9, csv_fields, parcels_cleaned_df)

    logging.debug('Creating centroid shapes...')
    parcels_with_centroids_df = helpers.add_centroids_to_parcel_df(parcels_merged_df, 'PARCEL_ID')

    davis_field_mapping = {
        'class': 'parcel_type',
    }
    standardized_parcels_df = helpers.standardize_fields(parcels_with_centroids_df, davis_field_mapping)

    #: Get a count of all parcels
    count_all = standardized_parcels_df.shape[0]
    logging.info(f'Initial parcels in modeling area:\t {count_all}')

    logging.debug('Classifying OUGs and MHCs...')
    #: Classify parcels within common areas
    common_area_key = 'common_area_key'
    common_areas_subset_df = helpers.subset_owned_unit_groupings_from_common_areas(common_areas_fc, common_area_key)

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
    oug_features_df = evaluations.owned_unit_groupings(classified_parcels_df, common_area_key, address_pts_no_base_df)

    logging.info('Evaluating single family parcels...')
    single_family_features_df = evaluations.single_family(classified_parcels_df)

    logging.info('Evaluating multi-family, single-parcel parcels...')
    multi_family_single_parcel_features_df = evaluations.multi_family_single_parcel(
        classified_parcels_df, address_pts_no_base_df
    )

    logging.info('Evaluating mobile home communities...')
    mobile_home_communities_features_df = evaluations.mobile_home_communities(
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

    helpers.update_unit_count(final_parcels_df)

    helpers.calculate_built_decade(final_parcels_df)

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
