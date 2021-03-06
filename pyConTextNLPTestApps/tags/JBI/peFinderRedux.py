#!/usr/bin/env python
#
#Licensed under the Apache License, Version 2.0 (the "License");
#you may not use this file except in compliance with the License.
#You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
#Unless required by applicable law or agreed to in writing, software
#distributed under the License is distributed on an "AS IS" BASIS,
#WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#See the License for the specific language governing permissions and
#limitations under the License.
"""peFinder is a program that processes the impression section of dictated
reports for CTPA exams. pyContext is used to look for descriptions of pulmonary embolisms.
The analysis looks for historical state, historicity, and uncertainty.

At this state, the program assumes that the reports are stored in a SQLite3 database.
The database is also presumed to contain user annotations, that the pyConText results
are compared to."""
import sys

import os
from optparse import OptionParser
import sqlite3 as sqlite

import datetime, time
import pyConText.pycontext as pycontext
import pyConText.helpers as helpers
from pyConText.pycontextSql import pycontextSql
import pyConText.pycontextNX as pnx
from pyConText.itemData import *
from peItemData import *
import cPickle

"""helper functions to compute final classification"""
def qualityState(value):
    if(value):
        return "Not Diagnostic"
    else:
        return "Diagnostic"
def diseaseState(value):
    if( value ):
        return "Pos"
    else:
        return "Neg"
def uncertaintyState(value):
    if( value ):
        return "Yes"
    else:
        return "No"
def notModifiedByOR(terms,modifier):
    for term in terms:
        if(not term.isModifiedBy(modifier)):
            return True
    return False
def historicalState(value):
    if( value ):
        return "Old"
    else:
        return "New"
def getParser():
    """Generates command line parser for specifying database and other parameters"""

    parser = OptionParser()
    parser.add_option("-d","--db",dest='dbname',
                      help='name of db containing reports to parse')
    parser.add_option("-o","--odb",dest='odbname',
                      help='name of db containing results')
    return parser



class PEContext(object):
    """This is the class definition that will contain the majority of processing
    algorithms for peFinder.
    
    The constructor takes as an argument the name fo an SQLite database containing
    the relevant information.
    """
    def __init__(self, dbname, outfile):
        """create an instance of a PEContext object associated with the SQLite
        database.
        dbname: name of SQLite database
        """

        # Define queries to select data from the SQLite database
        # this gets the reports we will process
        self.query1 = '''SELECT id,impression FROM pesubject''' 



        self.conn = sqlite.connect(dbname)
        self.cursor = self.conn.cursor()
        self.cursor.execute(self.query1)
        self.reports = self.cursor.fetchall()

        #conn = sqlite.connect("nx_o_context_differences.db")
        #curs = conn.cursor()
        #curs.execute("""select id from disease_diff""")
        #es = curs.fetchall()
        #errors = [e[0] for e in es]
        #
        #tmp = []
        #for r in self.reports:
        #    if r[0] in errors:
        #        print "removed"
        #        tmp.append(r)
        #self.reports = tmp
        
        
        print "number of reports to process",len(self.reports)
        t = time.localtime()
        d = datetime.datetime(t[0],t[1],t[2])
        
        # create context objects for each of the questions we want to be answering
        self.context = {"disease":pycontext.pycontext(),
                        "quality":pycontext.pycontext(),
                        "quality2":pycontext.pycontext()}


        rsltsDB = outfile
        if( os.path.exists(rsltsDB) ):
            os.remove(rsltsDB)
        
        self.resultsConn = sqlite.connect(rsltsDB)
        self.resultsCursor = self.resultsConn.cursor()
        self.resultsCursor.execute("""CREATE TABLE results (
            id INT PRIMARY KEY,
            disease TEXT,
            uncertainty TEXT,
            historical TEXT,
            quality TEXT)""")


        # Create the itemData object to store the modifiers for the  analysis
        # starts with definitions defined in pyConText and then adds
        # definitions specific for peFinder
        self.modifiers = {"disease":itemData.itemData()}
        self.modifiers["disease"].extend(pseudoNegations)
        self.modifiers["disease"].extend(definiteNegations)
        self.modifiers["disease"].extend(probableNegations)
        self.modifiers["disease"].extend(probables)
        self.modifiers["disease"].extend(definites)
        self.modifiers["disease"].extend(indications)
        self.modifiers["disease"].extend(historicals)
        self.modifiers["disease"].extend(conjugates)

        # Create a seperate itemData for the quality modifiers
        self.modifiers["quality"] = itemData.itemData()
        self.modifiers["quality"].extend(pseudoNegations)
        self.modifiers["quality"].extend(definiteNegations)
        self.modifiers["quality"].extend(probableNegations)
        self.modifiers["quality"].extend(probables)
        self.modifiers["quality"].extend(historicals)
        self.modifiers["quality"].extend(conjugates)
        self.modifiers["quality"].extend(qualities)
        self.modifiers["quality"].extend([['limited dataset compliant','EXCLUSION','','']])
        # Quality targets
        self.targets = {"disease":peItems}
        self.targets["quality"] = itemData.itemData()
        #self.targets["quality"].extend(qualities)
        self.targets["quality"].extend(examFeatures)
        self.targets["quality"].extend([['limited dataset compliant','EXCLUSION','','']])

        

        self.targets["quality2"] = itemData.itemData()
        self.targets["quality2"].extend(artifacts)
        self.temporalCount = 0
        self.models = {}



    def analyzePEReport(self, report, mode, modFilters = None ):
        """given an individual radiology report, creates a pyConTextSql
        object that contains the context markup

        report: a text string containing the radiology reports
        mode: ???
        modFilters: """
        context = self.context.get(mode)
        targets = self.targets.get(mode)
        modifiers = self.modifiers.get(mode)
        if modFilters == None :
            modFilters = ['indication','pseudoneg','probable_negated_existence',
                          'definite_negated_existence', 'probable_existence',
                          'definite_existence', 'historical']
        context.reset()
        terms = itemData.itemData(targets)
        sentences = helpers.sentenceSplitter(report)
        count = 0
        for s in sentences:
            context.setTxt(s) 
            if( modifiers ):
                context.markModifiers(modifiers)
            context.markTargets(terms)
            context.pruneMarks()
            context.dropMarks('Exclusion')
            context.applyModifiers()
            context.commit()
            count += 1
        model = pycontextSql()
        model.populate(context,modFilters)
        return model

    def createModel(self, sentence, mode, filters = None  ):

        self.models[mode] = self.analyzePEReport( sentence, mode,
                                modFilters=filters)
    def determineDiseaseState(self):
        """determine disease state for current object.
        Disease state will be positive if
            unmodifiedDisease is true OR modifiedDisease['quality'] is true
        """
        ds = diseaseState(bool(self.models["disease"].query(
            "where (unmodified == 'YES' or ((definite_existence == 'YES' or probable_existence == 'YES' ) and\
            pseudoneg == 'NO' and probable_negated_existence == 'NO' and\
            definite_negated_existence ==  'NO' and\
            indication == 'NO'))") or self.models["disease"].query(
            "where historical == 'YES' and probable_negated_existence == 'NO' and definite_negated_existence == 'NO'"
        ) ))
        

        self.disease_state = ds
    def determineQualityState(self):
        # now determine quality
        # quality is true (not-diagnostic) if modifiedQuality['quality'] is
        # true or if unmodifiedquality2 is true
        # make sure quality is uncertainty if no mention of PE is made
        # if finding is negated, don't mark as uncertain #265
        quality = bool(
            #self.models["quality"].query("where unmodified == 'YES'") or
            self.models["quality"].query("where quality_feature == 'YES'") or
            self.models["quality2"].query("where unmodified == 'YES'") ) 
        qs = qualityState(quality)
        self.quality_state = qs
        
    def determineUncertaintyState(self):
        # now determine disease uncertainty
        # uncertainty is true if modifiedDisease['uncertainty'] is true or
        # modifiedDisease[('negation','uncertainty')] or if the quality
        # is not diagnostic
        # uncertain if no mention of PE is made other than as indication fixes pedoc #155
        usd = bool(not self.models["disease"].query("") or \
                   (self.models["disease"].query("where indication == 'YES'") and \
                    not self.models["disease"].query("where probable_negated_existence == 'YES'") and\
                    not self.models["disease"].query("where definite_negated_existence == 'YES'") and\
                    not self.models["disease"].query("where probable_existence == 'YES'") ) )
        us = uncertaintyState(bool(
            self.models["disease"].query("where probable_negated_existence == 'YES' or probable_existence == 'YES' " ) or\
            self.models["disease"].query("where probable_existence == 'YES' and definite_negated_existence == 'YES'") or\
            (self.quality_state == "Not Diagnostic" and self.disease_state == 'Neg') or usd) )
        
        self.uncertainty_state = us
    def determineHistoricalState(self):
        if( self.disease_state == 'Neg'):
            self.historical_state = "NA"
        else:
            self.historical_state = historicalState(bool(self.models["disease"].query("where historical =='YES'")))
        
    def printContext(self):
        print "%6d\t%s\t%s\t%s"%(
                        self.currentCase,
                        self.disease_state.ljust(10).lower(),
                        self.quality_state.ljust(20).lower(),
                        self.uncertainty_state.ljust(5).lower())

    def processReports(self):
        """For the selected reports (training or testing) in the database,
        process each report with peFinder
        """
        count = 0
        for r in self.reports:
            self.currentCase = r[0]
            self.currentText = r[1].lower()            

            print self.currentCase
            # change program to only return one object
            # Essentialy move unmodifiedDisease into modifiedDiseae with a key of ''
            
            # I think we need to add a reference to the sentence to each tagged obect
            self.createModel(self.currentText, "disease", ['indication','probable_existence','definite_existence',
                                       'historical','pseudoneg','definite_negated_existence','probable_negated_existence'])
            self.createModel(self.currentText, "quality",['quality_feature'])
            self.createModel(self.currentText, "quality2")
            self.determineDiseaseState()
            self.determineQualityState()
            self.determineUncertaintyState()
            self.determineHistoricalState()
            count += 1

            self.recordResults()  
        print "processed %d cases"%count
    
    def recordResults(self):
        query = """INSERT INTO results (id,disease, uncertainty, historical, quality) VALUES (?,?,?,?,?)"""
        self.resultsCursor.execute(query,(self.currentCase,self.disease_state,self.uncertainty_state,self.historical_state,self.quality_state,))
        
        
    def cleanUp(self):     
        self.conn.close()
        self.resultsConn.commit()

        

def main():
    parser = getParser()
    (options, args) = parser.parse_args()
    if( options.dbname == options.odbname ):
        raise ValueError("output database must be distinct from input database")
        
    pec = PEContext(options.dbname, options.odbname)
    pec.processReports()
    pec.cleanUp()
    
    
if __name__=='__main__':
    main()
    
