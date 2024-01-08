from scraperunsv2 import *
from processruns import *

testSeries('data/redball.json', "xn02m872", 'Red Ball')
processRuns('data/redball.json', 'data/redball.csv', False)