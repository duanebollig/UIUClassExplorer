import os, asyncio, aiohttp, lxml, json, ollama
from typing import Literal
from urllib.parse import urljoin
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from bs4.element import Tag
from openai import AsyncOpenAI


load_dotenv()
BASE_URL = os.getenv("COURSEEXPLORERURL")

fileLock = asyncio.Lock()
CONCURRENCY_LIMIT = int(os.getenv("MAX_CONCURRENCY"))

OLLAMA_HOST = os.getenv("OLLAMA_HOST")
LLM_MODEL = os.getenv("LLM_MODEL")

YEAR = os.getenv("YEAR")
YEAR_URL = BASE_URL+YEAR

SEM_LLM = asyncio.Semaphore(2)
ollamaClient = ollama.AsyncClient(
    host=OLLAMA_HOST
)

SYS_PROMPT = (
    "you are an extractor of prerequisites, credits, and general education fulfillments from university courses given a paragraph"
    "return JSON only exactly with keys. NO PROSE, just the JSON:"
    '{"credit":(int),"prereq":(array of strings),"gened":(array of strings)}'
    "Rules:\n"
    "credit: if a single integer credit hour is stated (e.g., '3 hours.')\n"
    "prereq: return the course codes that follow the 'Prerequisite(s): ' string in uppercase. (e.g. 'ACES 220', 'CS 225')."
    "If there is not a specific class, return the sentence following the prerequisite string."
    "If there are no prerequisites, return a string 'N/A'.\n"
    "gen-ed: return the string of what general eduaction are fulfilled (e.g. 'Cultural Studies - US Minority.')."
    "If there are no gen-ed fulfillments, return a string 'N/A'.\n"
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
    messages = [
        {"role":"system","content":SYS_PROMPT},
        {"role":"user","content":paragraph}
    ]

    async with SEM_LLM:
        response = await ollamaClient.chat(
            model = LLM_MODEL,
            messages = messages,
            format = "json",
            options = {
                "temperature":0,
                "num_ctx": 4096,
                "keep_alive": "5m"
            }
        )
    
    rawJSON = response["message"]["content"]
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
        data = await scrapeHTML(session,url,param="datatext")
        async with fileLock:
            with open("courses.txt","a",encoding="utf-8") as f:
                for course in data:
                    f.write(
                        f"{data[course]["name"]} ({course}). {data[course]["link"]}\n"
                        f"Credit: {data[course]["credit"]}. Prereq(s): {data[course]["prereq"]}. Gen-Ed: {data[course]["gened"]}.\n\n"
                    )
        
        return data

async def main():
    sem = asyncio.Semaphore(CONCURRENCY_LIMIT)
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

        # RETURN COURSE INFO
        tasks = [controlledScrape(session,subjectList[sub]["link"],sem) for sub in subjectList]
        results = await asyncio.gather(*tasks)

        # SKIM THROUGH SUBJECT LIST
        courseDirectory = {}
        for result in results:
            courseDirectory.update(result)


asyncio.run(main())