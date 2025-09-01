import os, asyncio, aiohttp, lxml, json
from typing import Literal
from urllib.parse import urljoin
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from bs4.element import Tag
from openai import AsyncOpenAI


load_dotenv()
BASE_URL = os.getenv("COURSEEXPLORERURL")
CONCURRENCY_LIMIT = int(os.getenv("MAX_CONCURRENCY"))
API_KEY = os.getenv("OPENROUTER_APIKEY")
YEAR = os.getenv("YEAR")
YEAR_URL = BASE_URL+YEAR

llm = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=API_KEY
)

SYS_PROMPT = (
    "you are an extractor of prerequisites, credits, and general education fulfillments from university courses given a paragraph"
    "return JSON only exactly with keys:"
    '{"credit":(int),"prereq":(array of strings),"gened":(array of strings)}'
    "Rules:\n"
    "credit: if a single integer credit hour is stated (e.g., '3 hours.')\n"
    "prereq: return the course codes that follow the 'Prerequisite(s): ' string in uppercase. (e.g. 'ACES 220', 'CS 225')\n"
    "gend-ed: return the string of what general eduaction are fulfilled (e.g. 'Cultural Studies - US Minority.')"
)

async def getData(
        row: Tag,
        url: str
):
    rawData = row.find_all("td")
    courseCode = rawData[0].get_text(strip=True)
    courseName = rawData[1].get_text(strip=True)
    rawLink = row.select_one("a[href]").get("href")
    courseLink = urljoin(url,rawLink)

    return {
        "code":courseCode,
        "name":courseName,
        "link":courseLink
    }

async def llmProcess(
        paragraph: str
):
    response = await llm.chat.completions.create(
        model = "gpt-3.5-turbo",
        messages = [
            {"role":"system","content":SYS_PROMPT},
            {"role":"user","content":paragraph}
        ],
        temperature = 0,
        max_tokens = 160
    )

    rawJSON = response.choices[0].message.content
    processedJSON = json.loads(rawJSON)
    return processedJSON

paramsForScrape = Literal["datatext","data","only_link"]
async def scrapeHTML(
        session: aiohttp.ClientSession,
        url: str,
        param: paramsForScrape = "nodata"
    ):
    async with session.get(url) as response:
        html = await response.text()
        soup = BeautifulSoup(html,"lxml")
        rawRows = soup.select("table > tbody > tr")
        courseData = {}

        match param:
            case "datatext":
                for row in rawRows:
                    data = await getData(row,url)
                    dataDiv = ""
                    async with session.get(data["link"]) as dataResponse:
                        dataHTML = await dataResponse.text()
                        dataSoup = BeautifulSoup(dataHTML,"lxml")
                        dataDiv = dataSoup.find("div", id="app-course-info")
                        dataText = dataDiv.get_text(". ", strip=True) if dataDiv else "a"
                    
                    # LLM CLIENT
                    llmInfo = await llmProcess(dataText)

                    courseData[data["code"]] = {
                        "name": data["name"],
                        "link": data["link"],
                        "credit": llmInfo["credit"],
                        "prereq": llmInfo["prereq"],
                        "gened": llmInfo["gened"],
                    }

                return courseData

            case "data":
                for row in rawRows:
                    data = await getData(row,url)
                    courseData[data["code"]] = {
                        "name": data["name"],
                        "link": data["link"]
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
        for i,e in enumerate(semestersOffered):
            print(f"{i}) {e}")
        option = await asyncio.to_thread(input,"Enter Semester: ")
        option = int(option)

        # GET SUBJECTS OFFERED BY SEMESTER
        semesterLink = semestersOffered[option]
        subjectList = await scrapeHTML(session, semesterLink, param="data")

        # SKIM THROUGH SUBJECT LIST
        courseDirectory = {}
        for subject in subjectList:
            coursesBySubject = await scrapeHTML(session, subjectList[subject]["link"],param="datatext")
            courseDirectory.update(coursesBySubject)

        # WRTIE SUBJETCS
        with open("courses.txt","w",encoding="utf-8") as f:
            for course in courseDirectory:
                f.write(f"{courseDirectory[course]["name"]} ({course}). {courseDirectory[course]["link"]}\n")

asyncio.run(main())