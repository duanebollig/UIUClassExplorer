import os, asyncio, re
from contextlib import asynccontextmanager
from urllib.parse import urljoin
from dotenv import load_dotenv

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, BrowserContext, Page

load_dotenv()
BASE_URL = os.getenv("COURSEEXPLORERURL")
MAX_CONCURRENCY = int(os.getenv("MAX_CONCURRENCY"))

async def scrapePageCustom(
    context: BrowserContext,
    URL:str,
    query: str,
    param: str = None,
    select: bool = False
):
    page = await context.new_page()
    await page.goto(URL, wait_until="networkidle")
    content = await page.content()
    soup = BeautifulSoup(content,"lxml")

    if query == "preReq":
        rawTitle = await page.title()
        processedTitle = rawTitle.split("|")[0].strip()

        prereqText:str = None
        for p in soup.find_all("p"):
            rawText = p.get_text(" ", strip=True)
            if "Prerequisite" in rawText:
                prereqText = rawText[rawText.find(':')+1:].strip()

        return processedTitle,prereqText or "N/A"

    availableLinks = []
    if param:
        availableLinks = [e.get(param) for e in soup.select(query)]
    else:
        availableLinks = [e.get_text().strip() for e in soup.select(query)]
    
    if select:
        for i, e in enumerate(availableLinks):
            print(f"{i}) {e}")
        selectedLink = int(input("Enter Option: "))
        return urljoin(URL,availableLinks[selectedLink])
    else:
        return [urljoin(URL,link) for link in availableLinks]

async def controlledScrape(context: BrowserContext, URL: str, sem) -> str:
    async with sem:
        courseList = await scrapePageCustom(context, URL, "td a[href]","href")
        processedCourses: dict[str:str] = {}
        for course in courseList:
            title, prereq = await scrapePageCustom(context,course,"preReq")
            processedCourses[title] = prereq

        return processedCourses

async def main():
    async with async_playwright() as asp:
        browser = await asp.chromium.launch(headless=True)
        context = await browser.new_context()
        
        YEAR_URL = await scrapePageCustom(context,BASE_URL,"td a[href]","href",True)
        SEMESTER_URL = await scrapePageCustom(context,YEAR_URL,"td a[href]","href",True)
        SUBJECTLIST_URL = await scrapePageCustom(context,SEMESTER_URL,"td a[href]","href")

        sem = asyncio.Semaphore(MAX_CONCURRENCY)
        tasks = [controlledScrape(context, url, sem) for url in SUBJECTLIST_URL]
        results = await asyncio.gather(*tasks)

        await context.close()
        await browser.close()
        return results

rawData = asyncio.run(main())
processedData = {}
for d in rawData:
    processedData.update(d)

with open("courses.txt","w",encoding="utf-8") as f:
    for course in processedData:
        f.write(f"{course}: {processedData[course]}\n")