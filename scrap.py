#!/usr/bin/env python3

import datetime
import urllib
import sys
import time

import bs4
import pymongo
import requests



MAX_DOCS = 100
HTTP_ERROR_RETRY_DELAY = datetime.timedelta(minutes=1)
PROGRESS_TIMEOUT = datetime.timedelta(minutes=5)



def get_url(db):
    coll_urls = db["urls"]
    coll_logs = db["logs"]
    now = datetime.datetime.now()

    search = {
        "$or": [
            {"status": "pending"},
            {"status": "retry_later", "retry_at": {"$lte": now}},
            {"status": "inprogress", "started_at": {"$lte": now - PROGRESS_TIMEOUT}},
        ]
    }
    update_fields = {
        "status": "inprogress",
        "started_at": now
    }
    url = coll_urls.find_one_and_update(search, {"$set": update_fields})
    if url is None:
        return None

    log = {
        "date": now,
        "msg": f"Started processing url {url['url']} with scope f{url['scope']}",
        "url": url["url"],
        "scope": url["scope"]
    }
    coll_logs.insert_one(log)

    return url



def finished(db):
    coll_urls = db["urls"]
    notdone = coll_urls.count_documents({"status": {"$in": ["pending", "retry_later"]}})
    return notdone == 0



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



def ignored(db, urldoc):
    coll_urls = db["urls"]
    coll_logs = db["logs"]
    now = datetime.datetime.now()

    res = coll_urls.update_one({"_id": urldoc["_id"]}, {"$set": {"status": "ignored"}})

    log = {
        "date": now,
        "msg": f"Ignored {urldoc['url']} with scope {urldoc['scope']}",
        "url": urldoc["url"],
        "scope": urldoc["scope"],
        "update_result": res.raw_result
    }
    coll_logs.insert_one(log)



def store_new_links(db, doc, urldoc):
    coll_urls = db["urls"]
    coll_logs = db["logs"]

    links = doc.find_all("a")
    for link in links:
        href = urllib.parse.urljoin(urldoc["url"], link["href"])

        if not href.startswith(urldoc["scope"]):
            continue

        search = {
            "url": href,
            "scope": urldoc["scope"],
        }
        newurl = {
            "url": href,
            "scope": urldoc["scope"],
            "status": "pending",
            "added_at": datetime.datetime.now(),
            "started_at": None,
        }
        coll_urls.update_one(search, {"$setOnInsert": newurl}, upsert=True)



def store_doc(db, doc, urldoc, fetch_date):
    coll_docs = db["docs"]

    page_info = {
        "url": urldoc["url"],
        "scope": urldoc["scope"],
        "fetched_at": fetch_date,
        "html": str(doc),
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

    # This code would insert the page info only if it does not exist yet
    # Which might happen if a scraper was assumed broken (timeouted) when it
    # was just slow.
    #search = {"url": urldoc["url"], "scope": urldoc["scope"]}
    #coll_docs.update_one(search, {"$setOnInsert": page_info}, upsert=True)
    # Instead we just insert the document anyway
    coll_docs.insert_one(page_info)



def process_url(db, urldoc):
    print(f"scraping URL {urldoc['url']} with scope {urldoc['scope']}")
    coll_urls = db["urls"]
    coll_docs = db["docs"]
    coll_logs = db["logs"]

    ndocs = coll_docs.count_documents({"scope": urldoc["scope"]})
    # Parallel scappers may overshoot the limit a bit
    if ndocs >= MAX_DOCS:
        msg = f"Not fetching {urldoc['url']} in scope {urldoc['scope']} because there are already {ndocs} in this scope"
        print(msg)
        log = {
            "date": datetime.datetime.now(),
            "msg": msg,
            "url": urldoc["url"],
            "scope": urldoc["scope"],
            "ndocs": ndocs
        }
        coll_logs.insert_one(log)
        ignored(db, urldoc)
        return False

    res = requests.get(urldoc["url"])
    fetch_date = datetime.datetime.now()
    log = {
        "date": fetch_date,
        "msg": f"Getting URL {urldoc['url']} from scope {urldoc['scope']} got a response {res.status_code}, data size {len(res.content)}",
        "url": urldoc["url"],
        "scope": urldoc["scope"],
        "status": res.status_code,
        "content_size": len(res.content)
    }
    coll_logs.insert_one(log)

    if res.status_code != 200:
        try_count = urldoc.get("retry_count", 1)
        if try_count >= 10:
            update = {
                "status": "failed",
                "retry_at": None,
                "try_count": try_count
            }
        else:
            update = {
                "status": "retry_later",
                "retry_at": fetch_date + HTTP_ERROR_RETRY_DELAY,
                "try_count": try_count
            }
        coll_urls.update_one({"_id": urldoc["_id"]}, {"$set": update})
        return False

    doc = bs4.BeautifulSoup(res.text, "html.parser")
    store_doc(db, doc, urldoc, fetch_date)
    store_new_links(db, doc, urldoc)
    done(db, urldoc)
    return True



def main():
    client = pymongo.MongoClient("mongodb://localhost:27017/")
    db = client["seo"]

    while not finished(db):
        url_to_scrap = get_url(db)

        # Some urls might need to be retried later
        # Others might be "inprogress" but the scraper will fail eventually so
        # we just wait and see
        if url_to_scrap is None:
            time.sleep(1)
            continue

        process_url(db, url_to_scrap)

    print("No more URL to scrap")



if __name__ == "__main__":
    sys.exit(main())
