#!/usr/bin/env python3

import datetime
import urllib
import sys

import bs4
import pymongo
import requests



def get_url(db):
    coll_urls = db["urls"]
    coll_logs = db["logs"]
    now = datetime.datetime.now()

    # FIXME: race condition between find and update
    url = coll_urls.find_one({"status": "pending"})
    if url is None:
        return None

    update_fields = {
        "status": "inprogress",
        "started_at": now
    }
    coll_urls.update_one({"_id": url["_id"]}, {"$set": update_fields})

    log = {
        "date": now,
        "msg": f"Started processing url {url['url']} with scope f{url['scope']}",
        "url": url["url"],
        "scope": url["scope"]
    }
    coll_logs.insert_one(log)

    return url



def done(db, urldoc):
    coll_urls = db["urls"]
    coll_logs = db["logs"]
    now = datetime.datetime.now()

    res = coll_urls.update_one({"_id": urldoc["_id"]}, {"$set": {"status": "done"}})

    log = {
        "date": now,
        "msg": f"Done processing {urldoc['url']} with scope {urldoc['scope']}",
        "url": urldoc["url"],
        "scope": urldoc["scope"],
        "update_result": res.raw_result
    }
    coll_logs.insert_one(log)



def process_url(db, urldoc):
    print(f"scraping URL {urldoc['url']} with scope {urldoc['scope']}")
    coll_urls = db["urls"]
    coll_docs = db["docs"]
    coll_logs = db["logs"]

    res = requests.get(urldoc["url"])
    fetch_date = datetime.datetime.now()
    # TODO: handle errors during the request
    log = {
        "date": fetch_date,
        "msg": f"Getting URL {urldoc['url']} from scope {urldoc['scope']} got a response {res.status_code}, data size {len(res.content)}",
        "url": urldoc["url"],
        "scope": urldoc["scope"],
        "status": res.status_code,
        "content_size": len(res.content)
    }
    coll_logs.insert_one(log)

    doc = bs4.BeautifulSoup(res.text, "html.parser")

    page_info = {
        "url": urldoc["url"],
        "scope": urldoc["scope"],
        "fetched_at": fetch_date,
        "html": res.text,
        "title": doc.title.text.strip(),
        "emphasis": {
            "strong": [tag.text.strip() for tag in doc.find_all("strong")],
            "b": [tag.text.strip() for tag in doc.find_all("b")],
            "em": [tag.text.strip() for tag in doc.find_all("em")],
            "h1": [tag.text.strip() for tag in doc.find_all("h1")],
            "h2": [tag.text.strip() for tag in doc.find_all("h2")],
            "h3": [tag.text.strip() for tag in doc.find_all("h3")],
        }
    }
    coll_docs.insert_one(page_info)

    links = doc.find_all("a")
    for link in links:
        href = urllib.parse.urljoin(urldoc["url"], link["href"])

        if not href.startswith(urldoc["scope"]):
            continue

        if coll_urls.find_one({"url": href, "scope": urldoc["scope"]}):
            continue

        newurl = {
            "url": href,
            "scope": urldoc["scope"],
            "status": "pending",
            "added_at": datetime.datetime.now(),
            "started_at": None,
        }
        # FIXME: race condition here
        coll_urls.insert_one(newurl)




def main():
    client = pymongo.MongoClient("mongodb://localhost:27017/")
    db = client["seo"]

    while True:
        url_to_scrap = get_url(db)
        if url_to_scrap is None:
            break

        process_url(db, url_to_scrap)
        done(db, url_to_scrap)

    print("No more URL to scrap")



if __name__ == "__main__":
    sys.exit(main())
