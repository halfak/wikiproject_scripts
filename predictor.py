# -*- coding: utf-8 -*-
"""
Predicts article quality and priority with respect to a WikiProject.
Copyright (C) 2015 James Hare
Licensed under MIT License: http://mitlicense.org
"""


import datetime
import gzip
import json
import operator
import pywikibot
import re
import requests
from math import log  # https://www.youtube.com/watch?v=RTrAVpK9blw
from project_index import WikiProjectTools


def getviewdump(proj):
    '''
    Loads the page view dump for the past complete 30 days
    Takes string input (project name/abbreviation as identified in the dump)
    Returns a dict: title => pageviews
    '''

    # Create list of lists; each sub-list is a directory path
    # e.g. ['2015', '2015-06', '20150610-000000']

    filepaths = []
    for i in range(1, 32):  # day -1 through day -31 (i.e., thirty days in the past, starting with yesterday)
        time = datetime.datetime.now() + datetime.timedelta(-i)
        for j in range(24):  # for each hour
            hourminutesecond = '-' + str(j).zfill(2) + '0000'
            filepaths.append([time.strftime('%Y'), time.strftime('%Y-%m'), time.strftime('%Y%m%d') + hourminutesecond])

    # Read through each file, and if it matches with the project, append to output

    output = {}
    for file in filepaths:
        filename = '/public/dumps/pagecounts-raw/{0}/{1}/pagecounts-{2}.gz'.format(file[0], file[1], file[2])
        print("Loading: " + filename)
        with gzip.open(filename, mode='rt', encoding='utf-8') as f:
            content = f.read()

            content = content.split('\n')  # Splitting up by line
            for line in content:
                entry = line.split(' ')  # It's a space-delimited file, or something
                if entry[0] == proj:
                    if entry[1] in output:
                         output[entry[1]] += entry[2]  # Append to existing record
                    else:
                         output[entry[1]] = entry[2]  # Create new record
        print("Output dictionary is now " + str(len(output)) + " entries long.")

    return ouput


def getpageviews(dump, article):
    '''
    Queries *dump* for the number of page views in the last 30 days
    Takes dict *dump*, string *article* as input, returns view count.
    Does NOT take the logarithm of the view count.
    '''

    if article in dump:
        return dump[article]
    else:
        return 0

def getlinkcount(wptools, package):
    '''
    Gets a list of inbound links for a list of articles
    Takes list *package* as input, returns list of tuples (article, log of linkcount)
    Input MUST be a list. If there is just one article, enter it as such: [article]
    '''

    if len(package) > 1:
        query_builder = 'select pl_title, count(*) from pagelinks where pl_namespace = 0 and pl_title in {0} group by pl_title;'.format(tuple(package))
    else:
        query_builder = 'select pl_title, count(*) from pagelinks where pl_namespace = 0 and pl_title in {0} group by pl_title;'.format(package[0])

    output = []
    for row in wptools.query('wiki', query_builder, None):
        output.append((row[0].decode('utf-8'), log(row[1])))

    return output

class QualityPredictor:
    def qualitypredictor(self, pagetitle):
        print("Argh! Not ready yet!")
        # chat it up with ORES

class PriorityPredictor:
    def __init__(self, wikiproject, unknownpriority):
        print("Initializing the Priority Predictor for: " + wikiproject)
        self.wptools = WikiProjectTools()
        self.score = []  # Sorted list of tuples; allows for ranking
        self.score_unranked = {}  # Unsorted dictionary "article: value"; allows for easily looking up scores later

        # Preparing page view dump
        print("Loading pageview dump...")
        dump = getviewdump('en')

        # We need all the articles for a WikiProject, since the system works by comparing stats for an article to the others.
        print("Getting list of articles in the WikiProject...")
        self.articles = []   # List of strings (article titles)
        pageviews = []  # List of tuples (article title, log of view count)
        linkcount = []  # List of tuples (article title, log of link count)
        for row in self.wptools.query('index', 'select pi_page from projectindex where pi_project = "Wikipedia:{0}";'.format(wikiproject), None):
            if row[0].startswith("Talk:"):  # 
                article = row[0][5:] # Stripping out "Talk:"
                self.articles.append(article)

                # Page view count
                # Unfortunately, there is no way to batch this.
                print("Getting pageviews for: " + article)
                pageviews.append((article, log(getpageviews(dump, article))))

        # Inbound link count
        # This *is* batched, thus broken out of the loop
        print("Getting inbound link count...")
        packages = []
        for i in range(0, len(self.articles), 10000):
            packages.append(self.articles[i:i+10000])

        for package in packages:
                toappend = getlinkcount(self.wptools, package)
                for item in toappend:
                    linkcount.append(item)

        # Sorting...
        pageviews = sorted(pageviews, key=operator.itemgetter(1), reverse=True)
        linkcount = sorted(linkcount, key=operator.itemgetter(1), reverse=True)

        # Computing relative pageviews and linkcount
        # "Relative" means "as a ratio to the highest rank".
        # The most viewed article has a relative pageview score of 1.00. Goes lower from there.

        print("Computing relative pageviews and linkcount...")
        pageviews_relative = {}
        linkcount_relative = {}

        self.mostviews = pageviews[0][1]
        self.mostlinks = linkcount[0][1]

        for pair in pageviews:
            article = pair[0]
            count = pair[1]
            pageviews_relative[article] = count / self.mostviews

        for pair in linkcount:
            article = pair[0]
            count = pair[1]
            linkcount_relative[article] = count / self.mostlinks

        for article in self.articles:
            weightedscore = (pageviews_relative[article] * 0.75) + (linkcount_relative[article] * 0.25)
            self.score.append((article, weightscored))
            self.score_unranked[article] = weightedscore

        self.score = sorted(self.score, key=operator.itemgetter(1), reverse=True)

        # Calculating minimum scores
        # The idea is that there is a minimum score for something to be top, high, or mid-priority
        # The script is fed the category name for the unknown-importance/unknown-priority category
        # Based on this, derive category names for top/high/mid/low, add all the counts together...
        # ...then calculate ratio for top/high/mid as a ratio of the total...
        # ...multiply that ratio by the count of self.score, convert to an integer
        # ...and then threshold = self.score[that integer][1]
        # This gives us a general sense of what proportion of articles should be considered top/high/mid/low
        # Far from perfect but it's a start.

        print("Calculating priority thresholds...")
        toppriority = unknownpriority.replace("Unknown-", "Top-")
        highpriority = unknownpriority.replace("Unknown-", "High-")
        midpriority = unknownpriority.replace("Unknown-", "Mid-")
        lowpriority = unknownpriority.replace("Unknown-", "Low-")  # Easy enough...

        toppriority_count = self.wptools.query('wiki', 'select count(*) from categorylinks where cl_type = "page" and cl_to = {0}'.format(toppriority), None)[0][0]
        highpriority_count = self.wptools.query('wiki', 'select count(*) from categorylinks where cl_type = "page" and cl_to = {0}'.format(highpriority), None)[0][0]
        midpriority_count = self.wptools.query('wiki', 'select count(*) from categorylinks where cl_type = "page" and cl_to = {0}'.format(midpriority), None)[0][0]
        lowpriority_count = self.wptools.query('wiki', 'select count(*) from categorylinks where cl_type = "page" and cl_to = {0}'.format(lowpriority), None)[0][0]

        total_assessed = toppriority_count + highpriority_count + midpriority_count + lowpriority_count

        top_index = int((toppriority_count / total_assessed) * len(self.articles) - 1)
        high_index = int((highpriority_count / total_assessed) * len(self.articles) -1)
        mid_index = int((midpriority_count / total_assessed) * len(self.articles) -1)

        self.threshold_top = self.score[top_index][1]
        self.threshold_high = self.score[high_index][1]
        self.threshold_mid = self.score[mid_index][1]

    def prioritypredictor(self, pagetitle):
        # Pull pagescore if already defined
        # Otherwise, compute it "de novo"
        if pagetitle in self.articles:
            pagescore = self.score_unranked[pagetitle]
        else:
            pageviews = log(getpageviews(pagetitle)) / self.mostviews
            linkcount = getlinkcount([pagetitle])[0][1] / self.mostlinks
            pagescore = (pageviews * 0.75) + (linkcount * 0.25)

        if pagescore >= self.threshold_top:
            return "Top"

        if pagescore >= self.threshold_high:
            return "High"

        if pagescore >= self.threshold_mid:
            return "Mid"

        # If none of these...
        return "Low"