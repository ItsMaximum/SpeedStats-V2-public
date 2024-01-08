from scraperunsv2 import *
from processruns import *

exploreAll('data/runs.json')
processRuns('data/runs.json', 'data/runs.csv', False)
