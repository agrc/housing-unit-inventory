import logging
from pathlib import Path

import arcpy
import pandas as pd
from arcgis.features import GeoAccessor, GeoSeriesAccessor

from . import evaluations, helpers


def davis_county():

    arcpy.env.overwriteOutput = True

    #: Inputs
    input_dir_path = Path(r'c:\gis\git\housing_unit_inventory\Parcels\2020-Davis\Inputs')
    parcels_fc = input_dir_path / r'Davis_County_LIR_Parcels.gdb/Parcels_Davis_LIR_UTM12'
    address_pts = input_dir_path / r'AddressPoints_Davis.gdb\\address_points_davis'
    common_areas_fc = input_dir_path / r'Common_Areas.gdb\Common_Areas_Reviewed'
    extended_info_csv = input_dir_path / r'davis_extended_simplified.csv'
    mobile_home_communities = input_dir_path / r'Mobile_Home_Parks.shp'
    cities = input_dir_path / r'Cities.shp'
    subcounties = input_dir_path / r'SubCountyArea_2019.shp'

    #: Output
    output_dir_path = Path(r'c:\gis\projects\housinginventory')
    output_fc = output_dir_path / r'housinginventory.gdb\davis2020_1'
    output_csv = output_dir_path / r'davis2020_1.csv'

    #: Address points (used later)
    address_pts_no_base_df = helpers.get_non_base_addr_points(address_pts)

    #: Dissolve duplicate parcel ids
    logging.debug('Loading and dissolving parcels...')
    parcels_cleaned_df = helpers.load_and_clean_parcels(parcels_fc)

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

    #: Classify parcels within common areas
    logging.debug('Classifying OUGs and MHCs...')
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
    single_family_attributes = {
        'TYPE': 'single_family',
        'SUBTYPE': 'single_family',
        'basebldg': '1',
        'building_type_id': '1',
    }
    single_family_features_df = evaluations.by_parcel_types(
        classified_parcels_df, ['single_family'], single_family_attributes
    )

    logging.info('Evaluating multi-family, single-parcel parcels...')
    multi_family_types = ['multi_family', 'duplex', 'apartment', 'townhome', 'triplex-quadplex']
    multi_family_attributes = {
        'TYPE': 'multi_family',
        'basebldg': '1',
        'building_type_id': '2',
    }
    multi_family_single_parcel_features_df = evaluations.by_parcel_types(
        classified_parcels_df, multi_family_types, multi_family_attributes, address_pts_no_base_df,
        helpers.set_multi_family_single_parcel_subtypes
    )

    logging.info('Evaluating mobile home communities...')
    mobile_home_attributes = {
        'TYPE': 'multi_family',
        'SUBTYPE': 'mobile_home_park',
        'basebldg': '1',
    }
    mobile_home_communities_features_df = evaluations.by_parcel_types(
        classified_parcels_df, 'mobile_home_park', mobile_home_attributes, address_pts_no_base_df
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
