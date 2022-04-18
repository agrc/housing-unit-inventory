# Output Fields

## UNIT ID

WFRC created a unique ID here; this may make sense for datasets that include multiple counties. I'd like to use PARCEL_ID, or at least include PARCEL_ID in some form (maybe FIPs-prefixed? 11-PARCEL_ID?)

## TYPE

single_family or multi_family. Set manually in the evaluation for each subset of parcels.

## SUBTYPE

SUBTYPE comes from the common areas SUBTYPE_WFRC field for ougs, is set manually for single family homes, or comes from parcel_type (Davis' des_all) for single-parcel, multi-family parcels.

- If we want this to be comparable statewide, we need to come up with some sort of master/standardized list of types that each county's data are mapped to
- Otherwise, the set of SUBTYPEs will only be valid for each specific set of input data. Year-to-year comparisons will only be valid within each run (ie, you can look back in a dataset but you can't compare the dataset to a previous years' run).

## IS_OUG

WFRC uses a 1 or 0 here, but it came over as a text field so I'm using Yes/No

## UNIT_COUNT

Set manually for sf and duplex, tri/quad gets the HOUSE_CNT from the parcel data, and all others (ougs, mobile homes, multi-family) get the non-base address point count

## DUA

Dwelling units per acre. Recalculated acres (see below) divided by UNIT_COUNT

## ACRES

Acreage of parcel calculated from the parcel/oug geometry at the very end, after all dissolves and groupings have been done.

## TOT_BD_FT2

Total building sq ft. Comes from parcel's square footage either directly or summed for multi-parcel groupings.

## TOT_VALUE

Total assessed value. Comes from parcel's values either directly or summed for multi-parcel groupings.

## APX_BLT_YR

Approximate built year. Comes from parcel's values either directly or, for multi-parcel groupings, either the most common value or the latest if the most common is zero (ie, if there a bunch of under construction townhomes and one or two finished ones, it gets the date of the finished ones instead of the host of 0s).

## BLT_DECADE

Decade the parcel was developed. Just the first three digits of APX_BLT_YR * 10.

## CITY

City the parcel's centroid is in, based on SGID muni boundaries layer.

## COUNTY

Set manually.

## SUBCOUNTY

The subregion the parcel's centroid is in, based on file provided by WFRC/county for planning groupings/areas.

## PARCEL_ID

String value, because LIR specifies it is text, not numeric. Either a single parcel's PARCEL_ID or, for multi-parcel groupings, it is 99xxxx, where xxxx is either the common area key value used to identify the groupings or just a number between 0 and 9999. 99 was chosen because at least Cache reserves 99- numbers for common areas and other "fake" parcel IDs, so I'm hoping it's least likely to clash with real parcel IDs.

# Input Data

## Parcels

LIR parcels. Uses these fields:

- OBJECTID
- PARCEL_ID
- TOTAL_MKT_VALUE
- HOUSE_CNT
- BLDG_SQFT
- BUILT_YR
- SHAPE

Duplicate OIDs are dissolved on parcel ID using a custom dissolve that only sums attribute values if they are not the same (found some sliver parcels that duplicate the info for their parent parcel).

## Extended Parcel Info

From Assessor. For Davis, joins between AccountNo and Parcel ID.

- **class**             The detailed description of the parcel (sf, apartment, mobile home, etc). Renamed to parcel_type and used to filter out specific property types, set the SUBTYPEs
- **des_all**           Copied to NOTE field, used to identify tri/quad parcels

## Other Boundaries

From UGRC/MPOs

- **Municipalities**    Used to set the CITY field. Use SGID boundaries.
- **Subregions**        Used to set the SUBCOUNTY field to identify similar areas for planning/etc.

## Address Points

UT address points. Used to get unit count- need to have one point for every unit (apt, mobile home, condo, duplex, etc).Needs to have BASE ADDRESS info so we can filter out base addresses (HOA clubhouses, apartment offices, etc).

## Common Areas

Created. Used to identify areas that contribute to the value/acreage of multiple units (PUDs, condos, mobile homes, etc).

## Mobile Home Communities

Created. Used to identify any mobile home communities that are not identified as such in the assessor data or are split into multiple parcels.

# General Process

1. **Prep Parcels**
  a. Load parcels into memory
  a. Dissolve duplicate parcels
  a. Add any needed external data from assessor
  a. Create centroids of parcels for later spatial joins/summarize withins
1. **Classify Parcels**
  a. Subset provided owned unit grouping areas as needed to just residential areas
  a. Classify any parcels within owned unit grouping areas, adding a key unique to each area to each parcel whose centroid is within the area
  a. Classify any parcels within provided mobile home community areas
1. **Evaluate Parcels** (filter based on parcel_type)
  a. Owned unit groupings: Transfer/summarize attributes of parcels to the appropriate grouping area using the key established in the classify stage.
  a. Single family parcels: Just set some attributes directly
  a. Multi-family, single-parcel parcels: Set some attributes directly, calculate type/subtype, get unit count from address points
  a. Mobile home communities: Set some attributes directly, get unit count from address points
1. **Merge and Calculate**
  a. Merge all the evaluated parcel subgroups into a single dataset
  a. Calculate new parcel centroids, use to get CITY and SUBREGION
  a. Rename various fields, fill Nulls as appropriate
  a. Calculate acreages, unit density, year and decade built, floor counts
  a. Reindex fields to final desired fields.
  a. Write to both feature class and csv (minus shape field)

## Questions

- UNITID- county fips + parcel ID?
- 'basebldg', 'building_type_id'- needed?
- Use addr points to set unit count for du/tri/quadplex?
- Subtypes- unique? county-by-county? Merge to a statewide set?
