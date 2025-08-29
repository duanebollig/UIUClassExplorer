import os, asyncio, re, lxml, aiohttp
from typing import Literal
from urllib.parse import urljoin
from dotenv import load_dotenv
from playwright.async_api import async_playwright, BrowserContext
from bs4 import BeautifulSoup


load_dotenv()
BASE_URL = os.getenv("COURSEEXPLORERURL")
CONCURRENCY_LIMIT = int(os.getenv("MAX_CONCURRENCY"))
YEAR = os.getenv("YEAR")
YEAR_URL = BASE_URL+YEAR

paramsForScrape = Literal["text","data","only_link"]
async def scrapeHTML(
        session: aiohttp.ClientSession,
        url: str,
        param: paramsForScrape = "nodata"
    ):
    async with session.get(url) as response:
        html = await response.text()
        soup = BeautifulSoup(html,"lxml")

        match param:
            case "text":
                # rawP = soup.select("p")
                # WORK IN PROGRESS
                prereqLinks = soup.select("p a[href]")
                processedPrereqs = [link.get("href") for link in prereqLinks if "schedule" in link.get("href")]

                return processedPrereqs

            case "data":
                courseData = {}
                rawRows = soup.select("table > tbody > tr")

                for row in rawRows:
                    rawData = row.find_all("td")
                    courseCode = rawData[0].get_text(strip=True)
                    courseName = rawData[1].get_text(strip=True) 
                    rawLink = row.select_one("a[href]").get("href")
                    courseLink = urljoin(url,rawLink)

                    courseData[courseCode] = {
                        "name": courseName,
                        "link": courseLink
                    }

                return courseData
            
            case "only_link":
                rawData = soup.select("table > tbody > tr > td")
                courseLinks = [urljoin(url,row.select_one("a[href]").get("href")) for row in rawData]

                return courseLinks

async def controlledScrape(
        session: aiohttp.ClientSession,
        url: str,
        sem: asyncio.Semaphore
    ):

    async with sem:
        courseList = await scrapeHTML(session,url,preReq=True)
        for i in courseList:
            print(i)

async def main():
    async with aiohttp.ClientSession() as session:
        # GET SEMESTER URL
        semestersOffered = await scrapeHTML(session, YEAR_URL, param="only_link")
        print(semestersOffered)
        option = await asyncio.to_thread(input,"Enter Semester: ")
        option = int(option)

        # GET SUBJECTS OFFERED BY SEMESTER
        semesterLink = semestersOffered[option]
        subjectList = await scrapeHTML(session, semesterLink, param="data")

        # SKIM THROUGH SUBJECT LIST
        courseDirectory = {}
        for subject in subjectList:
            coursesBySubject = await scrapeHTML(session, subjectList[subject]["link"],param="data")
            courseDirectory.update(coursesBySubject)
        
        with open("courses.txt","w",encoding="utf-8") as f:
            for course in courseDirectory:
                f.write(f"{courseDirectory[course]["name"]} ({course}). {courseDirectory[course]["link"]}\n")


        

asyncio.run(main())