import os, asyncio, requests
from contextlib import asynccontextmanager
from urllib.parse import urljoin
from dotenv import load_dotenv

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, BrowserContext, Page

load_dotenv()
BASE_URL = os.getenv("COURSEEXPLORERURL")
MAX_CONCURRENCY = os.getenv("MAX_CONCURRENCY")

async def scrapePageLinks(context: BrowserContext, URL:str, query: str, param: str | None,  select: bool = False):
    page = await context.new_page()
    await page.goto(URL, wait_until="domcontentloaded")
    content = await page.content()

    soup = BeautifulSoup(content,"html.parser")
    availableLinks = []
    if param:
        availableLinks = [e.get(param) for e in soup.select(query)]
    else:
        availableLinks = [e.get_text().strip() for e in soup.select(query)]
    
    await page.close()

    if select:
        for i, e in enumerate(availableLinks):
            print(f"{i}) {e}")
        selectedLink = int(input("Enter Option: "))
        return urljoin(URL,availableLinks[selectedLink])
    else:
        return [urljoin(URL,link) for link in availableLinks]

async def controlledScrape(context: BrowserContext, URL: str, sem) -> str:
    async with sem:
        result = await scrapePageLinks(context, URL, "td a[href]","href")
        return result

async def main():
    async with async_playwright() as asp:
        browser = await asp.chromium.launch(headless=True)
        context = await browser.new_context()
        
        YEAR_URL = await scrapePageLinks(context,BASE_URL,"td a[href]","href",True)
        SEMESTER_URL = await scrapePageLinks(context,YEAR_URL,"td a[href]","href",True)
        SUBJECTLIST_URL = await scrapePageLinks(context,SEMESTER_URL,"td a[href]","href")

        sem = asyncio.Semaphore(MAX_CONCURRENCY)
        tasks = [controlledScrape(context, url, sem) for url in SUBJECTLIST_URL]
        results = await asyncio.gather(*tasks)

        # with open("courses.txt","w",encoding="utf-8") as f:
        #     for subject in results:
        #         for link in subject:
        #             f.write(f"{link}\n")

        await browser.close()


asyncio.run(main())