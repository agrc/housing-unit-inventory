import logging
from timeit import default_timer

from housing_unit_inventory import county_scripts


def process():

    start = default_timer()
    logging.basicConfig(level=logging.DEBUG)

    # import cProfile
    # import pstats

    # pr = cProfile.Profile()
    # pr.enable()

    county_scripts.davis_county()

    # pr.disable()
    # with open(r'c:\temp\davis_profile.txt', 'w+') as f:
    #     ps = pstats.Stats(pr, stream=f)
    #     ps.strip_dirs().sort_stats(-1).print_stats()

    end = default_timer()
    logging.debug(f'Total time: {end - start}')


if __name__ == '__main__':
    process()
