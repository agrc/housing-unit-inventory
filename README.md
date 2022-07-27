Create a housing unit inventory dataset for evaluating the makeup of a county's housing over time.

## Inputs

The inventory requires specific data about each parcel. Most of this should be captured in the county's [Land Information Record](https://gis.utah.gov/data/cadastre/parcels/#UtahLIRParcels) (LIR) parcels. Depending on the county, you may need supplemental info from the county assessor.

It can be difficult to properly evaluate density and value information for condos, townhomes, and other planned unit developments that incorporate a common base property or open space. The inventory relies on a custom-created dataset containing all the properties that contribute to each "owned unit grouping." This will need to be created on a county-by-county basis.

The inventory also uses the statewide [address points dataset](https://gis.utah.gov/data/location/address-data/) to determine the number of units for multi-unit properties. Any non-residential unit addresses within a multi-family development or other owned unit grouping (apartment offices, clubhouses, etc) need to be marked as base addresses. If these are not marked in the statewide layer, we'll need an updated layer from the county.

Finally, classification of mobile homes can be inconsistent sometimes. Some mobile home communities are owned as a single large parcel, while others can have each plot owned individually. The property class for these can also vary within a single community, making it hard to identify how mobile homes contribute to the overal housing mix. The inventory can use a custom-created mobile home community layer to ensure all mobile homes are classified properly.

## Outputs

The housing unit inventory outputs its data to both feature class and CSV. It includes the following fields:

- **UNIT ID**: A unique identifier for each parcel (may be derived from parcel IDs)
- **TYPE**: `single_family` or `multi_family`.
- **SUBTYPE**: Comes from the common areas SUBTYPE field for owned unit groupings, is set manually for single family homes, or comes from `parcel_type` for single-parcel, multi-family parcels.
- **IS_OUG**: Whether the feature is an owned unit grouping with aggregated values. Either `1`/`Yes` or `0`/`No`
- **UNIT_COUNT**: Number of units in the feature. Set manually for single family homes and duplexes and for all others (owned unit groupings, mobile homes, multi-family) it uses the address point count
- **DUA**: Dwelling units per acre. Recalculated acres (see below) divided by `UNIT_COUNT`
- **ACRES**: Acreage of feature calculated from the parcel/owned unit grouping geometry at the very end, after all dissolves and groupings have been done.
- **TOT_BD_FT2**: Total building sq ft. Comes from parcel's square footage either directly or summed for multi-parcel groupings.
- **TOT_VALUE**: Total assessed value. Comes from parcel's values either directly or summed for multi-parcel groupings.
- **APX_BLT_YR**: Approximate built year. Comes from parcel's values either directly or, for multi-parcel groupings, either the most common value or the latest if the most common is zero (ie, if there a bunch of under construction townhomes and only one or two finished ones, it gets the date of the finished ones instead of the host of 0s).
- **BLT_DECADE**: Decade the parcel was developed. Just the first three digits of `APX_BLT_YR` * 10.
- **CITY**: City the feature's center is in, based on the SGID [municipal boundaries layer](https://gis.utah.gov/data/boundaries/citycountystate/#MunicipalBoundaries).
- **COUNTY**: The county the feature is in, set manually in each county's analysis.
- **SUBCOUNTY**: The subregion the parcel's centroid is in, based on boundaries provided by the county for planning groupings/areas.
- **PARCEL_ID**: Either a single parcel's parcel ID or, for owned unit gropuings, it is `99xxxx`, where `xxxx` is either the common area ID used to identify the groupings or just a number between 0 and 9999.
