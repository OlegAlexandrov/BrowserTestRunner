import json, retrying, urllib
from selenium.webdriver.support.ui import WebDriverWait
from itertools import groupby
from xml.etree import ElementTree
from lib import log

webDriverWaitTimeout = 300


def runTests( driver, url, timeout ):

    # timeout is ignored

    log.write( "Calculating number of tests ... " )
    tests = getTests( driver, url )

    log.writeln( "%d tests found" % len( tests ) )

    testResults = []
    counter = 0

    for test in tests:

        retries = 5
        passed = False
        testResult = None
        counter += 1

        log.write( "Running test %d: %s ... " % ( counter, test ) )

        while not passed and retries:

            retries -= 1

            try:

                testResult = runTest( driver, "%s?spec=%s" % ( url, urllib.quote( test ) ) )

                if isPassed( testResult[ "json" ] ):
                    passed = True

            except Exception:

                log.writeln( "fatal error" )
                raise

        log.writeln( "passed" ) if passed else log.writeln( "failed" )
        testResults.append( testResult )

    suites = groupTestSuites( map( lambda x: x[ "json" ], testResults ) )
    xmlSuites = map( lambda x: ElementTree.tostring( x ), groupXmlSuites( map( lambda x: x[ "junit" ], testResults ) ) )

    testResults = {

        "json": {

            "suites": suites,
            "durationSec": sum( map( lambda x: x[ "durationSec" ], suites ) ),
            "passed": all( map( lambda x: x[ "passed" ], suites ) )
        },

        "junit": '<?xml version="1.0" encoding="UTF-8" ?>\n<testsuites>\n%s\n</testsuites>\n' % "\n".join( xmlSuites )
    }

    return testResults

@retrying.retry( stop_max_attempt_number = 5, wait_fixed = 5000 )
def getTests( driver, url ):

    driver.get( "%s?spec=SkipAll" % url )
    WebDriverWait( driver, webDriverWaitTimeout ).until( isFinished )

    selector = "return JSON.stringify( jasmine.getEnv().currentRunner().specs().map( function( spec ) { return spec.getFullName(); } ) )"
    specs = json.loads( driver.execute_script( selector ) )

    return specs

@retrying.retry( stop_max_attempt_number = 5, wait_fixed = 30000 )
def runTest( driver, url ):

    driver.get( url )
    WebDriverWait( driver, webDriverWaitTimeout ).until( isFinished )

    testResult = WebDriverWait( driver, webDriverWaitTimeout ).until( getResults )

    jsonResult = filterByDuration( testResult[ "suites" ] ).pop()
    reduceSuite( jsonResult )

    xmlResult = reduceXmlSuite( ElementTree.fromstring( WebDriverWait( driver, webDriverWaitTimeout ).until( getXmlResults ) ) )

    return {

        "json": jsonResult,
        "junit": xmlResult
    }

def isPassed( testResult ):

    while "suites" in testResult and len( testResult[ "suites" ] ):
        testResult = list( testResult[ "suites" ] ).pop()

    testResult = list( testResult[ "specs" ] ).pop()
    return testResult[ "passed" ]

def reduceSuite( parentSuite ):

    parentSuite[ "specs" ] = list( filter( lambda x: x[ "durationSec" ], parentSuite[ "specs" ] ) )
    parentSuite[ "suites" ] = filterByDuration( parentSuite[ "suites" ] )

    for suite in parentSuite[ "suites" ]:
        reduceSuite( suite )

def reduceXmlSuite( suites ):

    suite = max( list( suites.findall( 'testsuite' ) ), key=lambda s: float( s.attrib[ 'time' ] ) )

    for testcase in list( filter( lambda x: x.find( "skipped" ) is not None, suite ) ):
        suite.remove( testcase )

    return suite

def filterByDuration( items ):

    return list( filter( lambda item: item[ "durationSec" ] != 0, items ) )

def groupTestSuites( testSuites ):

    groupedSuites = []

    for description, group in groupby( testSuites, lambda x: x[ "description" ] ):

        group = list( group )
        suites = list( filter( lambda x: x.get( "suites" ), group ) )
        specs = list( filter( lambda x: x.get( "specs" ), group ) )
        childSuites = groupTestSuites( list( map( lambda x: list( x[ "suites" ] ).pop(), suites ) ) )
        childSpecs = list( map( lambda x: list( x[ "specs" ] ).pop(), specs ) )

        suite = {

            "description": description,
            "durationSec": sum( map( lambda x: x[ "durationSec" ], childSuites + childSpecs ) ),
            "passed": all( map( lambda x: x[ "passed" ], childSuites + childSpecs ) ),
            "suites": childSuites,
            "specs": childSpecs
        }

        groupedSuites.append( suite )

    return groupedSuites

def groupXmlSuites( suites ):

    groupedSuites = []

    for name, group in groupby( suites, lambda x: x.attrib[ "name" ] ):

        group = list( group )
        suite = ElementTree.Element( "testsuite" )
        suite.attrib[ "name" ] = name
        suite.attrib[ "errors" ] = str( sum( map( lambda x: int( x.attrib[ "errors" ] ), group ) ) )
        suite.attrib[ "failures" ] = str( sum( map( lambda x: int( x.attrib[ "failures" ] ), group ) ) )
        suite.attrib[ "time" ] = str( sum( map( lambda x: float( x.attrib[ "time" ] ), group ) ) )
        groups = list( filter( lambda x: len( x.getchildren() ), group ) )

        for testcase in map( lambda x: x.getchildren().pop(), groups ):
            suite.append( testcase )

        groupedSuites.append( suite )

    return groupedSuites

def isFinished( driver ):

  try:

    results = getResults( driver )

  except Exception:

    results = None

  try:

    xmlResults = getXmlResults( driver )

  except Exception:

    xmlResults = None

  return ( results is not None ) and ( xmlResults is not None )

def getResults( driver ):

  selector = "try { return JSON.stringify( jasmine.getJSReport() ) } catch ( e ) { return undefined }"
  results = driver.execute_script( selector )
  return json.loads( results ) if results else None

def getXmlResults( driver ):

  selector = ' try { return jasmine.JUnitXmlReporter.outputXml } catch ( e ) { return undefined }'
  results = driver.execute_script( selector )
  return results
