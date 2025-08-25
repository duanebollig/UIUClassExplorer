import os
import requests
from dotenv import load_dotenv
from flask import Flask,jsonify
from flask_cors import CORS
from urllib.parse import urljoin

import asyncio
from playwright.async_api import async_playwright
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

userYearSelected = input("What Year? ")

load_dotenv()
BASE_URL = f"{os.getenv('COURSEEXPLORERURL')}{userYearSelected}"

# app = Flask(__name__)
# CORS(app)

def obtainSemester():
    baseHTML = requests.get(BASE_URL)
    soup = BeautifulSoup(baseHTML.text,"html.parser")
    semestersOffered = {}
    print()
    for i,entry in enumerate(soup.select("td a[href]")):
        print(f"{i}) {entry.get_text().strip()}")
        link = entry.get("href")
        semestersOffered.update({i:link})
    semesterSelected = int(input("Enter Semester: "))
    print()

    return urljoin(BASE_URL,semestersOffered[semesterSelected])

def obtainSubjectLinkList():
    with sync_playwright() as syncplwr:
        browser = syncplwr.webkit.launch(headless=True)
        page = browser.new_page()
        semesterURL = obtainSemester()
        page.goto(semesterURL)

        subjectHTML = page.content()
        soup = BeautifulSoup(subjectHTML,"html.parser")
        return [urljoin(BASE_URL,entry.get("href")) for entry in soup.select("td a[href]")]


def scrapeCourseURLList():
    subjectLinkList = obtainSubjectLinkList()
    for i in subjectLinkList:
        print(i)
    # print(subjectLinkList)

if (__name__ == "__main__"):
    scrapeCourseURLList()